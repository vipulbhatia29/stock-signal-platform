import React from "react";
import { render, screen } from "@testing-library/react";
import { NewsCard } from "@/components/news-card";
import type { StockNewsResponse } from "@/types/api";

const mockNews: StockNewsResponse = {
  ticker: "AAPL",
  articles: [
    {
      title: "Apple announces new iPhone",
      link: "https://example.com/article1",
      publisher: "Reuters",
      published: new Date(Date.now() - 3600_000).toISOString(), // 1 hour ago
      source: "yfinance",
    },
    {
      title: "Apple beats earnings estimates",
      link: "https://example.com/article2",
      publisher: "Bloomberg",
      published: new Date(Date.now() - 86400_000).toISOString(), // 1 day ago
      source: "google_news",
    },
  ],
  fetched_at: new Date().toISOString(),
};

test("renders article titles as links", () => {
  render(<NewsCard news={mockNews} isLoading={false} />);
  const link1 = screen.getByText("Apple announces new iPhone");
  expect(link1.closest("a")).toHaveAttribute("href", "https://example.com/article1");
  expect(link1.closest("a")).toHaveAttribute("target", "_blank");
  expect(link1.closest("a")).toHaveAttribute("rel", "noopener noreferrer");
});

test("renders publisher names", () => {
  render(<NewsCard news={mockNews} isLoading={false} />);
  expect(screen.getByText("Reuters")).toBeInTheDocument();
  expect(screen.getByText("Bloomberg")).toBeInTheDocument();
});

test("renders loading skeleton", () => {
  const { container } = render(<NewsCard news={undefined} isLoading={true} />);
  expect(container.querySelectorAll("[data-slot='skeleton']").length).toBeGreaterThan(0);
});

test("renders empty state when no articles", () => {
  const emptyNews: StockNewsResponse = {
    ticker: "AAPL",
    articles: [],
    fetched_at: new Date().toISOString(),
  };
  render(<NewsCard news={emptyNews} isLoading={false} />);
  expect(screen.getByText(/no news/i)).toBeInTheDocument();
});

test("renders error state with retry", () => {
  const onRetry = jest.fn();
  render(<NewsCard news={undefined} isLoading={false} isError={true} onRetry={onRetry} />);
  expect(screen.getByText(/failed to load news/i)).toBeInTheDocument();
  expect(screen.getByText(/try again/i)).toBeInTheDocument();
});
