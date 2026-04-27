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

test("shows Bullish pill when sentimentLabel is bullish", () => {
  render(
    <NewsCard
      title="Stock surges after earnings beat"
      link="https://example.com"
      sentimentLabel="bullish"
    />
  );
  expect(screen.getByText("Bullish")).toBeInTheDocument();
});

test("shows Bearish pill when sentimentLabel is bearish", () => {
  render(
    <NewsCard
      title="Stock plunges on downgrade warning"
      link="https://example.com"
      sentimentLabel="bearish"
    />
  );
  expect(screen.getByText("Bearish")).toBeInTheDocument();
});

test("shows category badge for stock-specific news", () => {
  render(
    <NewsCard
      title="AAPL earnings beat"
      link="https://example.com"
      sentimentLabel="bullish"
      category="stock"
    />
  );
  expect(screen.getByText("Stock")).toBeInTheDocument();
});

test("no sentiment pill when sentimentLabel is neutral", () => {
  render(
    <NewsCard
      title="Market closes flat"
      link="https://example.com"
      sentimentLabel="neutral"
    />
  );
  expect(screen.queryByText("Bullish")).not.toBeInTheDocument();
  expect(screen.queryByText("Bearish")).not.toBeInTheDocument();
});
