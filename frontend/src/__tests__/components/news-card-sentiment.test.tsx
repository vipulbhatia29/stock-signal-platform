import React from "react";
import { render, screen } from "@testing-library/react";
import { NewsArticleCard as NewsCard } from "@/components/news-article-card";

test("renders title, publisher, and ticker", () => {
  render(
    <NewsCard
      title="AAPL reports quarterly earnings"
      publisher="Reuters"
      link="https://example.com"
      ticker="AAPL"
    />
  );
  expect(screen.getByText("AAPL reports quarterly earnings")).toBeInTheDocument();
  expect(screen.getByText("Reuters")).toBeInTheDocument();
  expect(screen.getByText("AAPL")).toBeInTheDocument();
});

test("shows Bullish pill for bullish headlines", () => {
  render(
    <NewsCard
      title="Stock surges after earnings beat"
      link="https://example.com"
    />
  );
  expect(screen.getByText("Bullish")).toBeInTheDocument();
});

test("shows Bearish pill for bearish headlines", () => {
  render(
    <NewsCard
      title="Stock plunges on downgrade warning"
      link="https://example.com"
    />
  );
  expect(screen.getByText("Bearish")).toBeInTheDocument();
});
