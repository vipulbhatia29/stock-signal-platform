import { render, screen, fireEvent } from "@testing-library/react";
import { AlertBell } from "@/components/alert-bell";

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@/components/ui/popover", () => ({
  Popover: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  PopoverTrigger: ({
    render: renderProp,
  }: {
    render?: React.ReactNode;
  }) => <div>{renderProp}</div>,
  PopoverContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

const mockMutate = jest.fn();

const mockAlerts = [
  {
    id: "1",
    alert_type: "divestment",
    severity: "critical" as const,
    title: "Stop-Loss Triggered",
    ticker: "TSLA",
    message: "Down 18.2% from cost basis",
    is_read: false,
    created_at: new Date().toISOString(),
    metadata: {},
  },
  {
    id: "2",
    alert_type: "signal_change",
    severity: "warning" as const,
    title: "Score Downgrade",
    ticker: "AAPL",
    message: "Dropped from 8.4 to 6.1",
    is_read: false,
    created_at: new Date().toISOString(),
    metadata: {},
  },
  {
    id: "3",
    alert_type: "pipeline",
    severity: "info" as const,
    title: "",
    ticker: null,
    message: "Pipeline completed",
    is_read: true,
    created_at: new Date(Date.now() - 86400000).toISOString(),
    metadata: {},
  },
];

jest.mock("@/hooks/use-alerts", () => ({
  useAlerts: () => ({
    data: {
      alerts: mockAlerts,
      total: 3,
      unreadCount: 2,
    },
    isLoading: false,
    isError: false,
  }),
  useMarkAlertsRead: () => ({
    mutate: mockMutate,
  }),
}));

describe("AlertBell", () => {
  beforeEach(() => {
    mockPush.mockClear();
    mockMutate.mockClear();
  });

  it("renders badge with unread count", () => {
    render(<AlertBell />);
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("shows all alert titles", () => {
    render(<AlertBell />);
    expect(screen.getByText("Stop-Loss Triggered")).toBeInTheDocument();
    expect(screen.getByText("Score Downgrade")).toBeInTheDocument();
  });

  it("renders critical severity with loss color", () => {
    render(<AlertBell />);
    const title = screen.getByText("Stop-Loss Triggered");
    expect(title.className).toContain("text-loss");
  });

  it("renders warning severity with warning color", () => {
    render(<AlertBell />);
    const title = screen.getByText("Score Downgrade");
    expect(title.className).toContain("text-warning");
  });

  it("falls back to alert_type when title is empty", () => {
    render(<AlertBell />);
    expect(screen.getByText("Pipeline")).toBeInTheDocument();
  });

  it("shows read alerts with reduced opacity", () => {
    render(<AlertBell />);
    const readAlert = screen
      .getByText("Pipeline completed")
      .closest("button");
    expect(readAlert?.className).toContain("opacity-60");
  });

  it("navigates to stock page on alert click with ticker", () => {
    render(<AlertBell />);
    fireEvent.click(screen.getByText("Down 18.2% from cost basis"));
    expect(mockPush).toHaveBeenCalledWith("/stocks/TSLA");
    expect(mockMutate).toHaveBeenCalledWith(["1"]);
  });

  it("does not navigate when alert has no ticker", () => {
    render(<AlertBell />);
    fireEvent.click(screen.getByText("Pipeline completed"));
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("shows ticker chip on alerts with ticker", () => {
    render(<AlertBell />);
    expect(screen.getByText("TSLA →")).toBeInTheDocument();
    expect(screen.getByText("AAPL →")).toBeInTheDocument();
  });

  it("shows Notifications header", () => {
    render(<AlertBell />);
    expect(screen.getByText("Notifications")).toBeInTheDocument();
  });

  it("shows Mark all read button", () => {
    render(<AlertBell />);
    expect(screen.getByText("Mark all read")).toBeInTheDocument();
  });

  it("shows View all notifications footer", () => {
    render(<AlertBell />);
    expect(
      screen.getByText("View all notifications →"),
    ).toBeInTheDocument();
  });
});
