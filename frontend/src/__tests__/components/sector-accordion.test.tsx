import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { SectorAccordion } from "@/components/sector-accordion";
import type { SectorSummary } from "@/types/api";

// Mock framer-motion to avoid animation issues in tests
jest.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => (
      <div {...props}>{children}</div>
    ),
  },
  AnimatePresence: ({ children }: React.PropsWithChildren) => <>{children}</>,
}));

const mockSector: SectorSummary = {
  sector: "Technology",
  stock_count: 42,
  avg_composite_score: 7.3,
  avg_return_pct: 12.5,
  your_stock_count: 3,
  allocation_pct: 35.2,
};

test("renders sector name and stock count", () => {
  render(
    <SectorAccordion sector={mockSector} isOpen={false} onToggle={() => {}}>
      <div>Content</div>
    </SectorAccordion>
  );
  expect(screen.getByText("Technology")).toBeInTheDocument();
  expect(screen.getByText("42 stocks")).toBeInTheDocument();
});

test("shows avg score", () => {
  render(
    <SectorAccordion sector={mockSector} isOpen={false} onToggle={() => {}}>
      <div>Content</div>
    </SectorAccordion>
  );
  expect(screen.getByText("7.3")).toBeInTheDocument();
});

test("shows your stock count when > 0", () => {
  render(
    <SectorAccordion sector={mockSector} isOpen={false} onToggle={() => {}}>
      <div>Content</div>
    </SectorAccordion>
  );
  expect(screen.getByText("3 yours")).toBeInTheDocument();
});

test("shows allocation percentage", () => {
  render(
    <SectorAccordion sector={mockSector} isOpen={false} onToggle={() => {}}>
      <div>Content</div>
    </SectorAccordion>
  );
  expect(screen.getByText("35.2%")).toBeInTheDocument();
});

test("calls onToggle when clicked", () => {
  const onToggle = jest.fn();
  render(
    <SectorAccordion sector={mockSector} isOpen={false} onToggle={onToggle}>
      <div>Content</div>
    </SectorAccordion>
  );
  fireEvent.click(screen.getByRole("button"));
  expect(onToggle).toHaveBeenCalledTimes(1);
});

test("shows children when isOpen is true", () => {
  render(
    <SectorAccordion sector={mockSector} isOpen={true} onToggle={() => {}}>
      <div>Expanded Content</div>
    </SectorAccordion>
  );
  expect(screen.getByText("Expanded Content")).toBeInTheDocument();
});
