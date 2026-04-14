import { render, screen } from "@testing-library/react";

import { StalenessBadge } from "@/components/staleness-badge";

describe("StalenessBadge", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date("2026-04-06T20:00:00Z"));
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("returns null when within SLA", () => {
    const recent = new Date("2026-04-06T19:00:00Z").toISOString();
    const { container } = render(<StalenessBadge lastUpdated={recent} slaHours={24} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders warning when stale", () => {
    const old = new Date("2026-04-05T00:00:00Z").toISOString();
    render(<StalenessBadge lastUpdated={old} slaHours={24} />);
    expect(screen.getByTestId("staleness-badge-stale")).toBeInTheDocument();
  });

  it("renders destructive when 2x stale", () => {
    const veryOld = new Date("2026-04-03T00:00:00Z").toISOString();
    render(<StalenessBadge lastUpdated={veryOld} slaHours={24} />);
    expect(screen.getByTestId("staleness-badge-very-stale")).toBeInTheDocument();
  });

  it("renders no-data when lastUpdated is null", () => {
    render(<StalenessBadge lastUpdated={null} slaHours={24} />);
    expect(screen.getByTestId("staleness-badge-none")).toBeInTheDocument();
  });

  it("renders refreshing when refreshing=true", () => {
    render(<StalenessBadge lastUpdated={null} slaHours={24} refreshing />);
    expect(screen.getByTestId("staleness-badge-refreshing")).toBeInTheDocument();
  });
});
