"""CLI health report — calls observability MCP tool functions and formats output.

Produces a Markdown (default) or JSON health report for quick platform inspection.
Shares the same data sources as the 13 MCP tools — different formatter, same queries.

Usage:
    # Full platform sweep — Markdown for copy-paste
    uv run python -m scripts.health_report --since=1h

    # Focused on a layer/provider
    uv run python -m scripts.health_report --layer=external_api --provider=yfinance --since=24h

    # Single trace deep-dive
    uv run python -m scripts.health_report --trace=abc-123

    # Anomalies only
    uv run python -m scripts.health_report --anomalies

    # Machine-readable JSON
    uv run python -m scripts.health_report --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from typing import Any

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data fetching — delegates to MCP tool functions
# ---------------------------------------------------------------------------


async def _fetch_full_report(since: str) -> dict[str, Any]:
    """Fetch platform health, anomalies, recent errors, and pipeline data.

    Args:
        since: Relative time window (e.g. "1h", "24h").

    Returns:
        Combined report data dict.
    """
    from backend.observability.mcp.anomalies import get_anomalies
    from backend.observability.mcp.external_api_stats import get_external_api_stats
    from backend.observability.mcp.platform_health import get_platform_health
    from backend.observability.mcp.recent_errors import get_recent_errors

    # Parse since into window_min for platform_health
    window_min = _since_to_minutes(since)

    health, anomalies, errors = await asyncio.gather(
        get_platform_health(window_min=window_min),
        get_anomalies(status="open", since=since),
        get_recent_errors(since=since, limit=100),
    )

    # Fetch external API stats for each provider mentioned in health
    ext_providers = _extract_providers(health)
    ext_stats = {}
    for provider in ext_providers:
        try:
            stats = await get_external_api_stats(provider=provider, window_min=max(window_min, 60))
            ext_stats[provider] = stats.get("result", {})
        except Exception:
            logger.debug("Failed to fetch external stats for %s", provider)

    return {
        "health": health,
        "anomalies": anomalies,
        "errors": errors,
        "external_stats": ext_stats,
    }


async def _fetch_anomalies_only(since: str) -> dict[str, Any]:
    """Fetch only anomaly findings.

    Args:
        since: Relative time window.

    Returns:
        Anomalies data dict.
    """
    from backend.observability.mcp.anomalies import get_anomalies

    return await get_anomalies(status="open", since=since)


async def _fetch_trace(trace_id: str) -> dict[str, Any]:
    """Fetch a single trace.

    Args:
        trace_id: The trace ID to look up.

    Returns:
        Trace data dict.
    """
    from backend.observability.mcp.trace import get_trace

    return await get_trace(trace_id=trace_id)


async def _fetch_layer_report(layer: str, provider: str | None, since: str) -> dict[str, Any]:
    """Fetch data filtered by layer, optionally by provider.

    Args:
        layer: Attribution layer to filter on.
        provider: Optional provider name.
        since: Relative time window.

    Returns:
        Layer-focused report data dict.
    """
    from backend.observability.mcp.external_api_stats import get_external_api_stats
    from backend.observability.mcp.recent_errors import get_recent_errors

    window_min = _since_to_minutes(since)
    subsystem_map = {
        "http": "http",
        "external_api": "external_api",
        "db": None,
        "cache": None,
        "celery": "celery",
        "frontend": "frontend",
        "agent": None,
    }
    subsystem = subsystem_map.get(layer)

    result: dict[str, Any] = {"layer": layer}

    if subsystem:
        errors = await get_recent_errors(subsystem=subsystem, since=since, limit=100)
        result["errors"] = errors

    if layer == "external_api" and provider:
        stats = await get_external_api_stats(provider=provider, window_min=max(window_min, 60))
        result["provider_stats"] = stats

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UNIT_MINUTES = {"m": 1, "h": 60, "d": 1440}


def _since_to_minutes(since: str) -> int:
    """Convert a relative time string to minutes.

    Args:
        since: Relative time string like "1h", "24h", "7d".

    Returns:
        Integer minutes.
    """
    import re

    match = re.match(r"^(\d+)(m|h|d)$", since)
    if not match:
        return 60
    value, unit = int(match.group(1)), match.group(2)
    return value * _UNIT_MINUTES[unit]


def _extract_providers(health: dict[str, Any]) -> list[str]:
    """Extract provider names from the platform health result.

    Args:
        health: Platform health envelope dict.

    Returns:
        List of provider name strings.
    """
    result = health.get("result", {})
    subsystems = result.get("subsystems", {})
    ext = subsystems.get("external_api", {})
    providers = ext.get("providers", {})
    return list(providers.keys())


# ---------------------------------------------------------------------------
# Markdown formatters
# ---------------------------------------------------------------------------


def _fmt_full_report(data: dict[str, Any], since: str) -> str:
    """Format a full platform health report as Markdown.

    Args:
        data: Combined report data from _fetch_full_report.
        since: Time window string for display.

    Returns:
        Markdown string.
    """
    lines: list[str] = []
    health = data["health"]
    anomalies = data["anomalies"]
    errors = data["errors"]
    ext_stats = data.get("external_stats", {})

    # Header
    h_result = health.get("result", {})
    overall = h_result.get("overall_status", "unknown")
    status_emoji = {"healthy": "green", "degraded": "yellow", "failing": "red"}.get(
        overall, "unknown"
    )
    lines.append(f"# Platform Health — last {since}")
    lines.append("")
    lines.append(f"## Status: {status_emoji.upper()} ({overall})")
    lines.append("")

    # Open anomalies
    findings = anomalies.get("result", {}).get("findings", [])
    if findings:
        lines.append(f"## Open Anomalies ({len(findings)})")
        for i, f in enumerate(findings, 1):
            sev = f.get("severity", "?")
            title = f.get("title", "Unknown")
            lines.append(f"{i}. **{title}** [{sev}]")
            evidence = f.get("evidence", {})
            if evidence:
                ev_parts = [f"{k}={v}" for k, v in list(evidence.items())[:4]]
                lines.append(f"   Evidence: {', '.join(ev_parts)}")
            hint = f.get("remediation_hint")
            if hint:
                lines.append(f"   Hint: {hint[:150]}")
        lines.append("")
    else:
        lines.append("## Open Anomalies (0)")
        lines.append("No open anomalies.")
        lines.append("")

    # Recent errors summary
    error_result = errors.get("result", {})
    error_items = error_result.get("errors", [])
    total_errors = errors.get("meta", {}).get("total_count", len(error_items))
    lines.append(f"## Recent Errors ({total_errors} in {since})")
    if error_items:
        by_source: dict[str, int] = {}
        for e in error_items:
            src = e.get("source", "unknown")
            by_source[src] = by_source.get(src, 0) + 1
        for src, count in sorted(by_source.items(), key=lambda x: -x[1]):
            lines.append(f"- {src}: {count} rows")
    else:
        lines.append("No recent errors.")
    lines.append("")

    # Pipeline health
    subsystems = h_result.get("subsystems", {})
    celery = subsystems.get("celery", {})
    pipelines = celery.get("recent_pipelines", [])
    if pipelines:
        lines.append("## Pipeline Health")
        for p in pipelines[:10]:
            name = p.get("pipeline_name", "?")
            status = p.get("status", "?")
            mark = "pass" if status in ("success", "no_op") else "FAIL"
            lines.append(f"- {name}: last status {status} [{mark}]")
        lines.append("")

    # External APIs
    if ext_stats:
        lines.append(f"## External APIs ({since})")
        lines.append("| Provider | Calls | Success | p95 lat | Errors | Cost |")
        lines.append("|---|---|---|---|---|---|")
        for provider, stats in ext_stats.items():
            current = stats.get("current_window", {})
            calls = current.get("total_calls", 0)
            success = current.get("success_rate", 0)
            success_pct = f"{success * 100:.1f}%" if isinstance(success, float) else str(success)
            p95 = current.get("p95_latency_ms", "?")
            p95_str = f"{p95}ms" if p95 != "?" else "?"
            errs = current.get("error_count", 0)
            cost = current.get("total_cost_usd", 0)
            cost_str = f"${cost:.2f}" if isinstance(cost, (int, float)) else str(cost)
            lines.append(
                f"| {provider} | {calls:,} | {success_pct} | {p95_str} | {errs} | {cost_str} |"
            )
        lines.append("")

    return "\n".join(lines)


def _fmt_anomalies(data: dict[str, Any]) -> str:
    """Format anomaly findings as Markdown.

    Args:
        data: Anomalies envelope dict.

    Returns:
        Markdown string.
    """
    lines: list[str] = []
    findings = data.get("result", {}).get("findings", [])
    lines.append(f"# Open Anomalies ({len(findings)})")
    lines.append("")
    if not findings:
        lines.append("No open anomalies.")
        return "\n".join(lines)

    for i, f in enumerate(findings, 1):
        sev = f.get("severity", "?")
        title = f.get("title", "Unknown")
        kind = f.get("kind", "?")
        layer = f.get("attribution_layer", "?")
        lines.append(f"### {i}. {title}")
        lines.append(f"- **Severity:** {sev} | **Kind:** {kind} | **Layer:** {layer}")
        evidence = f.get("evidence", {})
        if evidence:
            lines.append(f"- **Evidence:** {json.dumps(evidence, default=str)[:200]}")
        hint = f.get("remediation_hint")
        if hint:
            lines.append(f"- **Hint:** {hint}")
        lines.append("")

    return "\n".join(lines)


def _fmt_trace(data: dict[str, Any]) -> str:
    """Format a trace as Markdown.

    Args:
        data: Trace envelope dict.

    Returns:
        Markdown string.
    """
    lines: list[str] = []
    result = data.get("result", {})
    trace_id = result.get("trace_id", "?")
    lines.append(f"# Trace: {trace_id}")
    lines.append("")

    root = result.get("root_span")
    if not root:
        spans = result.get("spans", [])
        if not spans:
            lines.append("No spans found for this trace.")
            return "\n".join(lines)
        lines.append(f"**{len(spans)} spans** (flat — no root span identified)")
        lines.append("")
        for s in spans[:20]:
            kind = s.get("kind", "?")
            dur = s.get("duration_ms") or s.get("latency_ms", "?")
            lines.append(f"- [{kind}] {dur}ms — {s.get('detail', '')}")
        return "\n".join(lines)

    _fmt_span(root, lines, indent=0)
    return "\n".join(lines)


def _fmt_span(span: dict[str, Any], lines: list[str], indent: int, max_depth: int = 50) -> None:
    """Recursively format a span tree node.

    Args:
        span: Span dict with optional children.
        lines: Accumulator list of Markdown lines.
        indent: Current indentation depth.
        max_depth: Maximum recursion depth to prevent runaway trees.
    """
    if indent > max_depth:
        lines.append("  " * indent + "- ... (depth limit reached)")
        return
    prefix = "  " * indent
    kind = span.get("kind", "?")
    dur = span.get("duration_ms") or span.get("latency_ms", "?")
    status = span.get("status_code", "")
    detail_parts = [f"[{kind}]", f"{dur}ms"]
    if status:
        detail_parts.append(f"HTTP {status}")
    path = span.get("path", "")
    if path:
        detail_parts.append(path)
    error = span.get("error")
    if error:
        detail_parts.append(f"ERROR: {error}")

    lines.append(f"{prefix}- {' '.join(detail_parts)}")

    for child in span.get("children", []):
        _fmt_span(child, lines, indent + 1, max_depth)


def _fmt_layer_report(data: dict[str, Any], since: str) -> str:
    """Format a layer-focused report as Markdown.

    Args:
        data: Layer report data dict.
        since: Time window string for display.

    Returns:
        Markdown string.
    """
    lines: list[str] = []
    layer = data.get("layer", "?")
    lines.append(f"# Layer Report: {layer} — last {since}")
    lines.append("")

    errors = data.get("errors", {})
    if errors:
        error_items = errors.get("result", {}).get("errors", [])
        total = errors.get("meta", {}).get("total_count", len(error_items))
        lines.append(f"## Errors ({total})")
        for e in error_items[:20]:
            ts = e.get("timestamp", "?")
            msg = e.get("message", e.get("error_message", "?"))
            sev = e.get("severity", "?")
            lines.append(f"- [{sev}] {ts}: {str(msg)[:120]}")
        lines.append("")

    provider_stats = data.get("provider_stats", {})
    if provider_stats:
        result = provider_stats.get("result", {})
        current = result.get("current_window", {})
        lines.append("## Provider Stats")
        for k, v in current.items():
            lines.append(f"- **{k}:** {v}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        prog="health_report",
        description="Platform health report — calls observability MCP tools and formats output.",
    )
    parser.add_argument(
        "--since",
        default="1h",
        help="Relative time window (e.g. 1h, 24h, 7d). Default: 1h",
    )
    parser.add_argument(
        "--layer",
        choices=["http", "external_api", "db", "cache", "celery", "frontend", "agent"],
        help="Focus on a specific layer",
    )
    parser.add_argument(
        "--provider",
        help="Filter by external API provider (use with --layer=external_api)",
    )
    parser.add_argument(
        "--trace",
        metavar="TRACE_ID",
        help="Look up a single trace by ID",
    )
    parser.add_argument(
        "--anomalies",
        action="store_true",
        help="Show only open anomaly findings",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output raw JSON instead of Markdown",
    )
    return parser


async def _async_main(args: argparse.Namespace) -> None:
    """Async entry point for the health report.

    Args:
        args: Parsed CLI arguments.
    """
    if args.trace:
        data = await _fetch_trace(args.trace)
        if args.json_output:
            print(json.dumps(data, indent=2, default=str))
        else:
            print(_fmt_trace(data))
    elif args.anomalies:
        data = await _fetch_anomalies_only(args.since)
        if args.json_output:
            print(json.dumps(data, indent=2, default=str))
        else:
            print(_fmt_anomalies(data))
    elif args.layer:
        data = await _fetch_layer_report(args.layer, args.provider, args.since)
        if args.json_output:
            print(json.dumps(data, indent=2, default=str))
        else:
            print(_fmt_layer_report(data, args.since))
    else:
        data = await _fetch_full_report(args.since)
        if args.json_output:
            print(json.dumps(data, indent=2, default=str))
        else:
            print(_fmt_full_report(data, args.since))


def main() -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args()
    asyncio.run(_async_main(args))


if __name__ == "__main__":
    main()
