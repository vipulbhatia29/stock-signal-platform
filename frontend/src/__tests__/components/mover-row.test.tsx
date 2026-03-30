import React from "react";
import { render, screen } from "@testing-library/react";
import { MoverRow } from "@/components/mover-row";

test("renders ticker and formatted price", () => {
  render(<MoverRow ticker="TSLA" price={245.5} changePct={3.2} />);
  expect(screen.getByText("TSLA")).toBeInTheDocument();
  expect(screen.getByText("$245.50")).toBeInTheDocument();
});

test("shows MACD up arrow for bullish signal", () => {
  render(
    <MoverRow
      ticker="AAPL"
      changePct={1.5}
      macdSignal="Bullish Crossover"
    />,
  );
  expect(screen.getByText("MACD \u2191")).toBeInTheDocument();
});

test("shows MACD down arrow for bearish signal", () => {
  render(
    <MoverRow ticker="META" changePct={-2.0} macdSignal="bearish divergence" />,
  );
  expect(screen.getByText("MACD \u2193")).toBeInTheDocument();
});

test("applies gainer border for positive change", () => {
  const { container } = render(
    <MoverRow ticker="NVDA" changePct={5.1} />,
  );
  const button = container.firstChild as HTMLElement;
  expect(button.className).toContain("border-l-[var(--gain)]");
  expect(screen.getByText("+5.1%")).toBeInTheDocument();
});
