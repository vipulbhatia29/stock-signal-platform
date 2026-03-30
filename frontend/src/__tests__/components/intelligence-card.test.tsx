import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { IntelligenceCard } from "@/components/intelligence-card";
import type { StockIntelligenceResponse } from "@/types/api";

// Mock framer-motion
jest.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => (
      <div {...props}>{children}</div>
    ),
  },
  AnimatePresence: ({ children }: React.PropsWithChildren) => <>{children}</>,
}));

const mockIntelligence: StockIntelligenceResponse = {
  ticker: "AAPL",
  upgrades_downgrades: [
    {
      firm: "Goldman Sachs",
      to_grade: "Buy",
      from_grade: "Hold",
      action: "Upgrade",
      date: "2026-03-20",
    },
  ],
  insider_transactions: [
    {
      insider_name: "Tim Cook",
      relation: "CEO",
      transaction_type: "Sale",
      shares: 50000,
      value: 9500000,
      date: "2026-03-15",
    },
  ],
  next_earnings_date: "2026-04-25",
  eps_revisions: null,
  short_interest: {
    short_percent_of_float: 0.72,
    short_ratio: 1.5,
    shares_short: 120000000,
  },
  fetched_at: new Date().toISOString(),
};

test("renders summary row with earnings date and short interest", () => {
  render(<IntelligenceCard intelligence={mockIntelligence} isLoading={false} />);
  // Date may render as Apr 24 or Apr 25 depending on timezone
  expect(screen.getByText(/apr 2[45], 2026/i)).toBeInTheDocument();
  expect(screen.getAllByText(/0.72%/).length).toBeGreaterThanOrEqual(1);
});

test("renders analyst upgrade", () => {
  render(<IntelligenceCard intelligence={mockIntelligence} isLoading={false} />);
  // Expand the Analyst Ratings section
  const analystButton = screen.getByText(/analyst ratings/i);
  fireEvent.click(analystButton);
  expect(screen.getByText("Goldman Sachs")).toBeInTheDocument();
  expect(screen.getByText(/Buy/)).toBeInTheDocument();
});

test("renders insider transaction", () => {
  render(<IntelligenceCard intelligence={mockIntelligence} isLoading={false} />);
  const insiderButton = screen.getByText(/insider transactions/i);
  fireEvent.click(insiderButton);
  expect(screen.getByText("Tim Cook")).toBeInTheDocument();
  expect(screen.getByText("Sale")).toBeInTheDocument();
});

test("renders loading skeleton", () => {
  const { container } = render(
    <IntelligenceCard intelligence={undefined} isLoading={true} />
  );
  expect(container.querySelectorAll("[data-slot='skeleton']").length).toBeGreaterThan(0);
});

test("renders empty sub-sections gracefully", () => {
  const empty: StockIntelligenceResponse = {
    ...mockIntelligence,
    upgrades_downgrades: [],
    insider_transactions: [],
    short_interest: null,
    next_earnings_date: null,
  };
  render(<IntelligenceCard intelligence={empty} isLoading={false} />);
  expect(screen.getByText(/no upcoming earnings/i)).toBeInTheDocument();
});

test("renders error state with retry", () => {
  const onRetry = jest.fn();
  render(
    <IntelligenceCard
      intelligence={undefined}
      isLoading={false}
      isError={true}
      onRetry={onRetry}
    />
  );
  expect(screen.getByText(/failed to load intelligence data/i)).toBeInTheDocument();
});
