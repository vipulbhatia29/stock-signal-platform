import { render, screen, fireEvent } from "@testing-library/react";
import { WelcomeBanner } from "@/components/welcome-banner";
import { STORAGE_KEYS } from "@/lib/storage-keys";

// Mock useMounted to return true in test environment (jsdom)
jest.mock("@/hooks/use-mounted", () => ({
  useMounted: () => true,
}));

// Mock localStorage
const mockLocalStorage: Record<string, string> = {};
beforeEach(() => {
  Object.keys(mockLocalStorage).forEach((k) => delete mockLocalStorage[k]);
  jest.spyOn(Storage.prototype, "getItem").mockImplementation(
    (key: string) => mockLocalStorage[key] ?? null
  );
  jest.spyOn(Storage.prototype, "setItem").mockImplementation(
    (key: string, value: string) => {
      mockLocalStorage[key] = value;
    }
  );
});
afterEach(() => jest.restoreAllMocks());

describe("WelcomeBanner", () => {
  it("renders welcome message and suggested tickers", () => {
    const onAdd = jest.fn();
    render(<WelcomeBanner onAddTicker={onAdd} addingTickers={new Set()} />);
    expect(screen.getByText("Build your watchlist")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("NVDA")).toBeInTheDocument();
  });

  it("calls onAddTicker when a ticker button is clicked", () => {
    const onAdd = jest.fn();
    render(<WelcomeBanner onAddTicker={onAdd} addingTickers={new Set()} />);
    fireEvent.click(screen.getByText("AAPL"));
    expect(onAdd).toHaveBeenCalledWith("AAPL");
  });

  it("is hidden when dismissed", () => {
    const onAdd = jest.fn();
    render(<WelcomeBanner onAddTicker={onAdd} addingTickers={new Set()} />);
    fireEvent.click(screen.getByLabelText("Dismiss"));
    expect(screen.queryByText("Build your watchlist")).not.toBeInTheDocument();
    expect(mockLocalStorage[STORAGE_KEYS.ONBOARDING_DISMISSED]).toBe("true");
  });

  it("is hidden when localStorage says dismissed", () => {
    mockLocalStorage[STORAGE_KEYS.ONBOARDING_DISMISSED] = "true";
    const onAdd = jest.fn();
    render(<WelcomeBanner onAddTicker={onAdd} addingTickers={new Set()} />);
    expect(screen.queryByText("Build your watchlist")).not.toBeInTheDocument();
  });
});
