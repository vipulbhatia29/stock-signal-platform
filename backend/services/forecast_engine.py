"""LightGBM + XGBoost ensemble return forecasting engine."""

from __future__ import annotations

import io
import logging
import math
from datetime import date

import joblib
import lightgbm
import numpy as np
import pandas as pd
import shap
import xgboost
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

FEATURE_NAMES = [
    "momentum_21d",
    "momentum_63d",
    "momentum_126d",
    "rsi_value",
    "macd_histogram",
    "sma_cross",
    "bb_position",
    "volatility",
    "sharpe_ratio",
    "stock_sentiment",
    "sector_sentiment",
    "macro_sentiment",
    "sentiment_confidence",
    "signals_aligned",
    "convergence_label",
    "vix_level",
    "spy_momentum_21d",
]

FEATURE_LABELS = {
    "momentum_21d": "Recent price trend",
    "momentum_63d": "3-month momentum",
    "momentum_126d": "6-month momentum",
    "rsi_value": "Overbought/oversold level",
    "macd_histogram": "Trend strength",
    "sma_cross": "Moving average signal",
    "bb_position": "Price vs. trading range",
    "volatility": "Price volatility",
    "sharpe_ratio": "Risk-adjusted returns",
    "stock_sentiment": "News sentiment",
    "sector_sentiment": "Sector outlook",
    "macro_sentiment": "Economic outlook",
    "sentiment_confidence": "Sentiment confidence",
    "signals_aligned": "Signal agreement",
    "convergence_label": "Signal convergence",
    "vix_level": "Market fear index",
    "spy_momentum_21d": "Market trend",
}

LIGHTGBM_PARAMS = {
    "objective": "quantile",
    "metric": "quantile",
    "num_leaves": 31,
    "learning_rate": 0.05,
    "n_estimators": 500,
    "min_child_samples": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 0.1,
    "verbose": -1,
}

XGBOOST_PARAMS = {
    "objective": "reg:quantileerror",
    "max_depth": 6,
    "learning_rate": 0.05,
    "n_estimators": 500,
    "min_child_weight": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "verbosity": 0,
}

QUANTILES = [0.1, 0.5, 0.9]

# Convergence label encoding for ML models (string → numeric)
_CONVERGENCE_LABEL_MAP: dict[str | None, float] = {
    "strong_bullish": 2.0,
    "bullish": 1.0,
    "neutral": 0.0,
    "bearish": -1.0,
    "strong_bearish": -2.0,
    None: 0.0,
}


def _encode_convergence_label(val: str | None) -> float:
    """Encode convergence_label string to numeric for model input.

    Args:
        val: Convergence label string or None.

    Returns:
        Numeric encoding of the label.
    """
    if isinstance(val, float) and math.isnan(val):
        return 0.0
    return _CONVERGENCE_LABEL_MAP.get(val, 0.0)  # type: ignore[arg-type]


def _features_to_array(features: dict) -> pd.DataFrame:
    """Convert a feature dict to a single-row DataFrame for prediction.

    Encodes ``convergence_label`` to numeric and fills missing values with NaN
    so that LightGBM / XGBoost handle them natively.  Returning a DataFrame
    (rather than a bare numpy array) preserves feature names and eliminates
    the "X does not have valid feature names" sklearn warning.

    Args:
        features: Mapping of feature name → value.

    Returns:
        Single-row DataFrame with columns matching ``FEATURE_NAMES``.
    """
    row = []
    for name in FEATURE_NAMES:
        val = features.get(name)
        if name == "convergence_label":
            row.append(_encode_convergence_label(val))  # type: ignore[arg-type]
        elif val is None:
            row.append(float("nan"))
        else:
            row.append(float(val))
    return pd.DataFrame([row], columns=list(FEATURE_NAMES))  # type: ignore[arg-type]  # pandas stubs


def _prepare_feature_df(df: pd.DataFrame) -> pd.DataFrame:
    """Encode string/categorical columns in a training DataFrame.

    Args:
        df: Raw training DataFrame with FEATURE_NAMES columns.

    Returns:
        DataFrame with ``convergence_label`` encoded to float.
    """
    result = df.copy()
    if "convergence_label" in result.columns:
        result["convergence_label"] = result["convergence_label"].apply(_encode_convergence_label)
    return result.astype(float)


class ForecastEngine:
    """Stateless LightGBM + XGBoost ensemble for stock return forecasting.

    All model state is passed in and out as bytes artifacts via joblib
    serialization — the engine itself holds no instance state.
    """

    # ------------------------------------------------------------------
    # Data assembly
    # ------------------------------------------------------------------

    async def assemble_features_bulk(
        self,
        tickers: list[str],
        as_of_date: date,
        db: AsyncSession,
    ) -> dict[str, dict]:
        """Fetch the latest feature vector for each ticker from historical_features.

        Performs a single bulk query (no N+1). For any tickers not found in
        ``historical_features`` for the given date the ticker is omitted from
        the returned mapping.

        Args:
            tickers: List of ticker symbols to fetch.
            as_of_date: The date to look up features for.
            db: Async SQLAlchemy session.

        Returns:
            Mapping of ticker → feature dict (keys are FEATURE_NAMES).
        """
        from backend.models.historical_feature import HistoricalFeature  # noqa: PLC0415

        stmt = select(HistoricalFeature).where(
            HistoricalFeature.ticker.in_(tickers),
            HistoricalFeature.date == as_of_date,
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        out: dict[str, dict] = {}
        for row in rows:
            out[row.ticker] = {name: getattr(row, name, None) for name in FEATURE_NAMES}
        return out

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(
        self,
        features_df: pd.DataFrame,
        horizon_days: int,
        weights: dict | None = None,
    ) -> tuple[bytes, dict]:
        """Train a LightGBM + XGBoost quantile ensemble.

        Uses an expanding-window walk-forward CV (12-month initial window,
        1-month step) to produce out-of-fold metrics before fitting the final
        models on the full dataset.

        Args:
            features_df: DataFrame with columns matching FEATURE_NAMES plus
                ``forward_return_{horizon_days}d`` as the target column.
            horizon_days: Forecast horizon in days (e.g. 60 or 90).
            weights: Optional dict with keys ``lgb`` and ``xgb`` for ensemble
                weighting. Defaults to equal weights (0.5 / 0.5).

        Returns:
            Tuple of (artifact_bytes, metrics_dict). artifact_bytes is a
            joblib-serialised dict keyed as ``"lgb_q0.1"``, ``"xgb_q0.5"``,
            etc. metrics_dict contains ``direction_accuracy``,
            ``mean_absolute_error``, and ``ci_containment``.
        """
        target_col = f"forward_return_{horizon_days}d"
        if target_col not in features_df.columns:
            raise ValueError(f"Target column '{target_col}' not found in DataFrame")

        # Purge rows with missing target (boundary buffer)
        clean = features_df.dropna(subset=[target_col]).copy()
        if len(clean) < 10:
            raise ValueError(f"Insufficient training rows after purging NaN targets: {len(clean)}")

        X = _prepare_feature_df(clean[list(FEATURE_NAMES)])  # type: ignore[arg-type]  # pandas indexing returns DataFrame
        y = clean[target_col].astype(float).values

        w_lgb = (weights or {}).get("lgb", 0.5)
        w_xgb = (weights or {}).get("xgb", 0.5)

        # Walk-forward CV metrics accumulators
        oof_preds_q01: list[np.ndarray] = []
        oof_preds_q50: list[np.ndarray] = []
        oof_preds_q09: list[np.ndarray] = []
        oof_actuals: list[np.ndarray] = []

        n = len(clean)
        initial_window = min(int(n * 0.6), max(20, n - 5))
        step = max(1, n // 10)

        for split_end in range(initial_window, n, step):
            train_X = X.iloc[:split_end]
            train_y = y[:split_end]
            val_X = X.iloc[split_end : split_end + step]
            val_y = y[split_end : split_end + step]
            if len(val_X) == 0:
                break

            fold_preds_q50 = np.zeros(len(val_X))
            fold_preds_q01 = np.zeros(len(val_X))
            fold_preds_q09 = np.zeros(len(val_X))

            for q in QUANTILES:
                lgb_model = lightgbm.LGBMRegressor(**{**LIGHTGBM_PARAMS, "alpha": q})
                lgb_model.fit(train_X, train_y)
                xgb_model = xgboost.XGBRegressor(**{**XGBOOST_PARAMS, "quantile_alpha": q})
                xgb_model.fit(train_X, train_y)

                preds = w_lgb * lgb_model.predict(val_X) + w_xgb * xgb_model.predict(val_X)
                if q == 0.1:
                    fold_preds_q01 = preds
                elif q == 0.5:
                    fold_preds_q50 = preds
                else:
                    fold_preds_q09 = preds

            oof_preds_q01.append(fold_preds_q01)
            oof_preds_q50.append(fold_preds_q50)
            oof_preds_q09.append(fold_preds_q09)
            oof_actuals.append(val_y)  # type: ignore[arg-type]  # numpy array append

        # Compute OOF metrics
        if oof_actuals:
            all_actuals = np.concatenate(oof_actuals)
            all_q50 = np.concatenate(oof_preds_q50)
            all_q01 = np.concatenate(oof_preds_q01)
            all_q09 = np.concatenate(oof_preds_q09)

            direction_acc = float(np.mean(np.sign(all_q50) == np.sign(all_actuals)))
            mae = float(np.mean(np.abs(all_q50 - all_actuals)))
            ci_containment = float(np.mean((all_actuals >= all_q01) & (all_actuals <= all_q09)))
        else:
            direction_acc = 0.0
            mae = 0.0
            ci_containment = 0.0

        metrics = {
            "direction_accuracy": direction_acc,
            "mean_absolute_error": mae,
            "ci_containment": ci_containment,
        }

        # Train final models on full dataset
        bundle: dict[str, object] = {}
        for q in QUANTILES:
            lgb_model = lightgbm.LGBMRegressor(**{**LIGHTGBM_PARAMS, "alpha": q})
            lgb_model.fit(X, y)
            bundle[f"lgb_q{q}"] = lgb_model

            xgb_model = xgboost.XGBRegressor(**{**XGBOOST_PARAMS, "quantile_alpha": q})
            xgb_model.fit(X, y)
            bundle[f"xgb_q{q}"] = xgb_model

        buf = io.BytesIO()
        joblib.dump(bundle, buf)
        artifact_bytes = buf.getvalue()

        return artifact_bytes, metrics

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(
        self,
        features: dict,
        model_artifact: bytes,
        weights: dict | None = None,
        compute_shap: bool = True,
    ) -> dict:
        """Run ensemble prediction for a single ticker feature vector.

        Args:
            features: Dict mapping feature name → value (may contain NaN).
            model_artifact: Bytes produced by :meth:`train`.
            weights: Optional ``{"lgb": float, "xgb": float}`` for weighting.
            compute_shap: When ``False``, skip SHAP driver computation and
                return ``drivers=None``.  Use for non-priority tickers where
                SHAP overhead is not warranted (spec finding O2).

        Returns:
            Dict with keys: ``expected_return_pct``, ``return_lower_pct``,
            ``return_upper_pct``, ``direction``, ``confidence``,
            ``confidence_level``, ``drivers``, ``forecast_signal``.
        """
        bundle: dict = joblib.load(io.BytesIO(model_artifact))
        X = _features_to_array(features)

        w_lgb = (weights or {}).get("lgb", 0.5)
        w_xgb = (weights or {}).get("xgb", 0.5)

        preds: dict[float, float] = {}
        for q in QUANTILES:
            lgb_pred = bundle[f"lgb_q{q}"].predict(X)[0]
            xgb_pred = bundle[f"xgb_q{q}"].predict(X)[0]
            preds[q] = w_lgb * lgb_pred + w_xgb * xgb_pred

        # Convert log returns → simple return percentages
        expected_return_pct = (math.exp(preds[0.5]) - 1.0) * 100.0
        return_lower_pct = (math.exp(preds[0.1]) - 1.0) * 100.0
        return_upper_pct = (math.exp(preds[0.9]) - 1.0) * 100.0

        interval_width = abs(preds[0.9] - preds[0.1])
        signals_aligned = int(features.get("signals_aligned") or 0)

        vix = features.get("vix_level")
        if vix is None or (isinstance(vix, float) and math.isnan(vix)):
            vix_regime = "normal"
        elif float(vix) < 15:
            vix_regime = "low"
        elif float(vix) > 25:
            vix_regime = "high"
        else:
            vix_regime = "normal"

        confidence = self.compute_confidence(interval_width, signals_aligned, vix_regime)
        direction = self.classify_direction(expected_return_pct)
        conf_level = self.confidence_level(confidence)
        forecast_signal = self.compute_forecast_signal(direction, confidence, signals_aligned)

        # Use q=0.5 LGB model for SHAP drivers (median, interpretable).
        # Skip when compute_shap=False for non-priority tickers (spec O2).
        if compute_shap:
            median_lgb_model = bundle["lgb_q0.5"]
            drivers: list[dict] | None = self.explain_top_drivers(features, median_lgb_model)
        else:
            drivers = None

        return {
            "expected_return_pct": expected_return_pct,
            "return_lower_pct": return_lower_pct,
            "return_upper_pct": return_upper_pct,
            "direction": direction,
            "confidence": confidence,
            "confidence_level": conf_level,
            "drivers": drivers,
            "forecast_signal": forecast_signal,
        }

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------

    def compute_confidence(
        self,
        interval_width: float,
        signals_aligned: int,
        vix_regime: str,
    ) -> float:
        """Compute a calibrated confidence score for a forecast.

        Combines prediction interval tightness, signal agreement, and VIX
        regime into a single [0.2, 0.95]-clamped score.

        Args:
            interval_width: Absolute width of the 10–90 quantile interval
                (in log-return units).
            signals_aligned: Number of signals pointing in the same direction
                (0–6 scale).
            vix_regime: One of ``"low"``, ``"normal"``, or ``"high"``.

        Returns:
            Confidence score clamped to [0.2, 0.95].
        """
        interval_tightness = 1.0 - interval_width / 0.5
        signal_agreement = signals_aligned / 6.0
        regime_factor = 1.0 if vix_regime == "low" else 0.8 if vix_regime == "normal" else 0.6
        confidence = 0.4 * interval_tightness + 0.35 * signal_agreement + 0.25 * regime_factor
        return max(0.2, min(0.95, confidence))

    # ------------------------------------------------------------------
    # SHAP drivers
    # ------------------------------------------------------------------

    def explain_top_drivers(
        self,
        features: dict,
        model: object,
        top_n: int = 3,
    ) -> list[dict]:
        """Return the top N SHAP-based feature drivers for a single prediction.

        Args:
            features: Feature dict for a single observation.
            model: A fitted LightGBM or XGBoost sklearn-API model.
            top_n: Number of top drivers to return.

        Returns:
            List of dicts with keys ``feature``, ``label``, ``direction``,
            and ``importance`` (normalised absolute SHAP value).
        """
        X = _features_to_array(features)
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X)

        # shap_values may be 2-D (1 × n_features) or 1-D
        if hasattr(shap_values, "ndim") and shap_values.ndim == 2:
            sv = shap_values[0]
        else:
            sv = np.asarray(shap_values).flatten()

        abs_sv = np.abs(sv)
        total = abs_sv.sum()

        indices = np.argsort(abs_sv)[::-1][:top_n]
        drivers = []
        for idx in indices:
            name = FEATURE_NAMES[idx]
            shap_val = float(sv[idx])
            importance = float(abs_sv[idx] / total) if total > 0 else 0.0
            drivers.append(
                {
                    "feature": name,
                    "label": FEATURE_LABELS[name],
                    "direction": "bullish" if shap_val > 0 else "bearish",
                    "importance": importance,
                }
            )
        return drivers

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def classify_direction(expected_return_pct: float) -> str:
        """Classify expected return as bullish, bearish, or neutral.

        Boundaries are exclusive: exactly ±1.0% is classified as neutral.

        Args:
            expected_return_pct: Expected return in percentage points.

        Returns:
            ``"bullish"``, ``"bearish"``, or ``"neutral"``.
        """
        if expected_return_pct > 1.0:
            return "bullish"
        if expected_return_pct < -1.0:
            return "bearish"
        return "neutral"

    @staticmethod
    def compute_forecast_signal(
        direction: str,
        confidence: float,
        signals_aligned: int,
    ) -> str:
        """Classify the overall forecast signal based on direction + confidence.

        Args:
            direction: One of ``"bullish"``, ``"bearish"``, ``"neutral"``.
            confidence: Confidence score in [0, 1].
            signals_aligned: Number of aligned signals (0–6).

        Returns:
            ``"supports_buy"``, ``"supports_caution"``, or
            ``"insufficient_conviction"``.
        """
        high_conf = confidence >= 0.70
        high_align = signals_aligned >= 4
        if high_conf and high_align and direction == "bullish":
            return "supports_buy"
        if high_conf and high_align and direction == "bearish":
            return "supports_caution"
        return "insufficient_conviction"

    @staticmethod
    def confidence_level(score: float) -> str:
        """Convert a numeric confidence score to a human-readable level.

        Args:
            score: Confidence score in [0, 1].

        Returns:
            ``"high"`` (≥0.70), ``"medium"`` (≥0.45), or ``"low"``.
        """
        if score >= 0.70:
            return "high"
        if score >= 0.45:
            return "medium"
        return "low"
