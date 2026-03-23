import { createContext, useContext, useState, useCallback, useMemo, type ReactNode } from "react";
import { MOCK_ALL_STOCKS, simulateStockRefresh, type WatchlistStock } from "@/lib/mock-data";

interface StockRefreshContextType {
  /** Live stock data map — always read from here instead of MOCK_ constants */
  stocks: Map<string, WatchlistStock>;
  /** Ordered array of all stocks */
  allStocks: WatchlistStock[];
  /** Last refresh timestamp per ticker */
  lastRefreshed: Record<string, Date>;
  /** Whether a specific ticker is currently refreshing */
  refreshing: Record<string, boolean>;
  /** Refresh a single stock */
  refreshStock: (ticker: string) => void;
  /** Refresh all tracked stocks */
  refreshAll: () => void;
  /** Whether a bulk refresh is in progress */
  refreshingAll: boolean;
}

const StockRefreshContext = createContext<StockRefreshContextType | null>(null);

// Simulate stale data: some stocks refreshed recently, others days ago
function generateInitialTimestamps(): Record<string, Date> {
  const map: Record<string, Date> = {};
  MOCK_ALL_STOCKS.forEach((s, i) => {
    const hoursAgo = i < 2 ? 0.5 : i < 5 ? 6 : 24 * (i + 1);
    map[s.ticker] = new Date(Date.now() - hoursAgo * 3600000);
  });
  return map;
}

function buildStockMap(stocks: WatchlistStock[]): Map<string, WatchlistStock> {
  const m = new Map<string, WatchlistStock>();
  stocks.forEach((s) => m.set(s.ticker, s));
  return m;
}

export function StockRefreshProvider({ children }: { children: ReactNode }) {
  const [stockList, setStockList] = useState<WatchlistStock[]>(() => [...MOCK_ALL_STOCKS]);
  const [lastRefreshed, setLastRefreshed] = useState<Record<string, Date>>(generateInitialTimestamps);
  const [refreshing, setRefreshing] = useState<Record<string, boolean>>({});
  const [refreshingAll, setRefreshingAll] = useState(false);

  const stocks = useMemo(() => buildStockMap(stockList), [stockList]);

  const refreshStock = useCallback((ticker: string) => {
    setRefreshing((prev) => ({ ...prev, [ticker]: true }));
    // Simulate backend job latency
    setTimeout(() => {
      setStockList((prev) =>
        prev.map((s) => (s.ticker === ticker ? simulateStockRefresh(s) : s))
      );
      setLastRefreshed((prev) => ({ ...prev, [ticker]: new Date() }));
      setRefreshing((prev) => ({ ...prev, [ticker]: false }));
    }, 800 + Math.random() * 600);
  }, []);

  const refreshAll = useCallback(() => {
    setRefreshingAll(true);
    const allTickers = stockList.map((s) => s.ticker);
    allTickers.forEach((t) => setRefreshing((prev) => ({ ...prev, [t]: true })));
    // Stagger completion
    allTickers.forEach((ticker, i) => {
      setTimeout(() => {
        setStockList((prev) =>
          prev.map((s) => (s.ticker === ticker ? simulateStockRefresh(s) : s))
        );
        setLastRefreshed((prev) => ({ ...prev, [ticker]: new Date() }));
        setRefreshing((prev) => ({ ...prev, [ticker]: false }));
        if (i === allTickers.length - 1) setRefreshingAll(false);
      }, 600 + i * 150);
    });
  }, [stockList]);

  return (
    <StockRefreshContext.Provider value={{
      stocks,
      allStocks: stockList,
      lastRefreshed,
      refreshing,
      refreshStock,
      refreshAll,
      refreshingAll,
    }}>
      {children}
    </StockRefreshContext.Provider>
  );
}

export function useStockRefresh() {
  const ctx = useContext(StockRefreshContext);
  if (!ctx) throw new Error("useStockRefresh must be used within StockRefreshProvider");
  return ctx;
}
