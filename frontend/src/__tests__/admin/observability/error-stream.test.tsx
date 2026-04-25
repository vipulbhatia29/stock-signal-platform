import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  LayerPill,
  SeverityBadge,
  ErrorRow,
  FiltersBar,
} from "@/app/(authenticated)/admin/observability/_components/error-stream";
import { formatRelativeTime } from "@/app/(authenticated)/admin/observability/_components/shared";
import type { ErrorEntry } from "@/types/admin-observability";

// ---------------------------------------------------------------------------
// formatRelativeTime
// ---------------------------------------------------------------------------

describe("formatRelativeTime", () => {
  beforeAll(() => jest.useFakeTimers());
  afterAll(() => jest.useRealTimers());

  test("returns seconds when < 60s ago", () => {
    const now = new Date("2026-04-24T12:00:30Z");
    jest.setSystemTime(now);
    expect(formatRelativeTime("2026-04-24T12:00:00Z")).toBe("30s ago");
  });

  test("returns minutes when 60s-3599s ago", () => {
    const now = new Date("2026-04-24T12:05:00Z");
    jest.setSystemTime(now);
    expect(formatRelativeTime("2026-04-24T12:00:00Z")).toBe("5m ago");
  });

  test("returns hours when >= 3600s ago", () => {
    const now = new Date("2026-04-24T14:00:00Z");
    jest.setSystemTime(now);
    expect(formatRelativeTime("2026-04-24T12:00:00Z")).toBe("2h ago");
  });
});

// ---------------------------------------------------------------------------
// LayerPill
// ---------------------------------------------------------------------------

test("LayerPill renders correct label for http", () => {
  render(<LayerPill source="http" />);
  expect(screen.getByText("HTTP")).toBeInTheDocument();
});

test("LayerPill renders correct label for external_api", () => {
  render(<LayerPill source="external_api" />);
  expect(screen.getByText("External API")).toBeInTheDocument();
});

test("LayerPill renders correct label for celery", () => {
  render(<LayerPill source="celery" />);
  expect(screen.getByText("Celery")).toBeInTheDocument();
});

// ---------------------------------------------------------------------------
// SeverityBadge
// ---------------------------------------------------------------------------

test("SeverityBadge renders 'error' label", () => {
  render(<SeverityBadge severity="error" />);
  expect(screen.getByText("error")).toBeInTheDocument();
});

test("SeverityBadge renders 'warning' label", () => {
  render(<SeverityBadge severity="warning" />);
  expect(screen.getByText("warning")).toBeInTheDocument();
});

// ---------------------------------------------------------------------------
// ErrorRow
// ---------------------------------------------------------------------------

const BASE_ENTRY: ErrorEntry = {
  source: "http",
  ts: new Date(Date.now() - 5000).toISOString(),
  message: "Internal server error",
  severity: "error",
  trace_id: "abc-123",
  stack_signature: null,
  details: {},
};

test("ErrorRow renders message, layer pill, and severity badge", () => {
  const onOpenTrace = jest.fn();
  render(<ErrorRow entry={BASE_ENTRY} onOpenTrace={onOpenTrace} />);
  expect(screen.getByText("Internal server error")).toBeInTheDocument();
  expect(screen.getByText("HTTP")).toBeInTheDocument();
  expect(screen.getByText("error")).toBeInTheDocument();
});

test("ErrorRow renders trace button when trace_id is present", () => {
  const onOpenTrace = jest.fn();
  render(<ErrorRow entry={BASE_ENTRY} onOpenTrace={onOpenTrace} />);
  expect(screen.getByRole("button", { name: /open trace abc-123/i })).toBeInTheDocument();
});

test("ErrorRow calls onOpenTrace with trace_id when trace button clicked", async () => {
  const onOpenTrace = jest.fn();
  render(<ErrorRow entry={BASE_ENTRY} onOpenTrace={onOpenTrace} />);
  await userEvent.click(screen.getByRole("button", { name: /open trace abc-123/i }));
  expect(onOpenTrace).toHaveBeenCalledWith("abc-123");
});

test("ErrorRow hides trace button when trace_id is null", () => {
  const onOpenTrace = jest.fn();
  const entry: ErrorEntry = { ...BASE_ENTRY, trace_id: null };
  render(<ErrorRow entry={entry} onOpenTrace={onOpenTrace} />);
  expect(screen.queryByRole("button", { name: /open trace/i })).not.toBeInTheDocument();
});

test("ErrorRow truncates long messages and expands on click", async () => {
  const onOpenTrace = jest.fn();
  const longMsg = "A".repeat(100);
  const entry: ErrorEntry = { ...BASE_ENTRY, message: longMsg };
  render(<ErrorRow entry={entry} onOpenTrace={onOpenTrace} />);

  // Initially truncated
  expect(screen.getByText(`${"A".repeat(80)}\u2026`)).toBeInTheDocument();

  // Click the message button to expand
  await userEvent.click(screen.getByText(`${"A".repeat(80)}\u2026`));
  expect(screen.getByText(longMsg)).toBeInTheDocument();
});

test("ErrorRow shows fallback text when message is null", () => {
  const onOpenTrace = jest.fn();
  const entry: ErrorEntry = { ...BASE_ENTRY, message: null };
  render(<ErrorRow entry={entry} onOpenTrace={onOpenTrace} />);
  expect(screen.getByText("(no message)")).toBeInTheDocument();
});

// ---------------------------------------------------------------------------
// FiltersBar
// ---------------------------------------------------------------------------

test("FiltersBar renders all filter controls", () => {
  const onChange = jest.fn();
  const filters = { layer: "", severity: "", since: "1h", traceSearch: "" };
  render(<FiltersBar filters={filters} onChange={onChange} />);

  expect(screen.getByRole("combobox", { name: /filter by layer/i })).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: /filter by severity/i })).toBeInTheDocument();
  expect(screen.getByRole("searchbox", { name: /search by trace id/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "1h" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "6h" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "24h" })).toBeInTheDocument();
});

test("FiltersBar calls onChange with updated layer when select changes", async () => {
  const onChange = jest.fn();
  const filters = { layer: "", severity: "", since: "1h", traceSearch: "" };
  render(<FiltersBar filters={filters} onChange={onChange} />);
  await userEvent.selectOptions(
    screen.getByRole("combobox", { name: /filter by layer/i }),
    "http"
  );
  expect(onChange).toHaveBeenCalledWith({ ...filters, layer: "http" });
});

test("FiltersBar calls onChange with updated since when time button clicked", async () => {
  const onChange = jest.fn();
  const filters = { layer: "", severity: "", since: "1h", traceSearch: "" };
  render(<FiltersBar filters={filters} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "6h" }));
  expect(onChange).toHaveBeenCalledWith({ ...filters, since: "6h" });
});

test("FiltersBar calls onChange with traceSearch when input changes", async () => {
  const onChange = jest.fn();
  const filters = { layer: "", severity: "", since: "1h", traceSearch: "" };
  render(<FiltersBar filters={filters} onChange={onChange} />);
  await userEvent.type(
    screen.getByRole("searchbox", { name: /search by trace id/i }),
    "abc"
  );
  // Each keystroke triggers onChange — check last call
  const calls = onChange.mock.calls;
  expect(calls[calls.length - 1][0].traceSearch).toBe("c");
});
