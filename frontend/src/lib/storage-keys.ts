// Centralised localStorage key registry — all keys namespaced with "stocksignal:"
// to prevent collisions with browser extensions and future features.
export const STORAGE_KEYS = {
  CHAT_PANEL_WIDTH: "stocksignal:cp-width",
  SCREENER_DENSITY: "stocksignal:density",
} as const;
