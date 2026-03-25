/**
 * Shared data-testid constants for E2E tests.
 * Add new selectors here as tests are authored.
 */
export const SELECTORS = {
  // Layout
  SIDEBAR_NAV: "sidebar-nav",
  TOPBAR: "topbar",
  LOADING_SPINNER: "loading-spinner",

  // Auth
  LOGIN_EMAIL: "login-email",
  LOGIN_PASSWORD: "login-password",
  LOGIN_SUBMIT: "login-submit",
  LOGIN_ERROR: "login-error",
  LOGOUT_BUTTON: "logout-button",

  // Dashboard
  STAT_TILE: "stat-tile",
  REFRESH_ALL: "refresh-all",
  TRENDING_STOCKS: "trending-stocks",

  // Chat
  CHAT_INPUT: "chat-input",
  CHAT_SEND: "chat-send",
  CHAT_MESSAGE: "chat-message",
  CHAT_TOOL_STEP: "chat-tool-step",

  // Stock Detail
  SIGNAL_CARD: "signal-card",
  PRICE_CHART: "price-chart",
  FUNDAMENTALS_CARD: "fundamentals-card",

  // Screener
  SCREENER_TABLE: "screener-table",
  SCREENER_ROW: "screener-row",
} as const;
