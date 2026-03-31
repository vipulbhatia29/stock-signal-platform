import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { DrillDownSheet } from "@/components/command-center/drill-down-sheet";

// Mock the Sheet primitives to avoid @base-ui/react dependency issues in test
jest.mock("@/components/ui/sheet", () => ({
  Sheet: ({ open, children }: { open: boolean; children: React.ReactNode }) =>
    open ? <div data-testid="sheet-root">{children}</div> : null,
  SheetContent: ({
    children,
  }: {
    children: React.ReactNode;
    side?: string;
    className?: string;
    showCloseButton?: boolean;
  }) => <div data-testid="sheet-content">{children}</div>,
  SheetHeader: ({
    children,
  }: {
    children: React.ReactNode;
    className?: string;
  }) => <div data-testid="sheet-header">{children}</div>,
  SheetTitle: ({
    children,
  }: {
    children: React.ReactNode;
    className?: string;
  }) => <h2>{children}</h2>,
}));

jest.mock("@/components/ui/button", () => ({
  Button: ({
    children,
    onClick,
    ...props
  }: React.ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: string;
    size?: string;
  }) => (
    <button onClick={onClick} {...props}>
      {children}
    </button>
  ),
}));

describe("DrillDownSheet", () => {
  const onClose = jest.fn();
  const onRefresh = jest.fn();

  afterEach(() => jest.clearAllMocks());

  it("renders children when open", () => {
    render(
      <DrillDownSheet open onClose={onClose} title="Test Sheet">
        <p>Sheet content here</p>
      </DrillDownSheet>,
    );
    expect(screen.getByText("Sheet content here")).toBeInTheDocument();
    expect(screen.getByText("Test Sheet")).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    render(
      <DrillDownSheet open={false} onClose={onClose} title="Hidden">
        <p>Hidden content</p>
      </DrillDownSheet>,
    );
    expect(screen.queryByText("Hidden content")).not.toBeInTheDocument();
  });

  it("renders refresh button and calls onRefresh", async () => {
    const user = userEvent.setup();
    render(
      <DrillDownSheet
        open
        onClose={onClose}
        title="Refresh Test"
        onRefresh={onRefresh}
      >
        <p>Body</p>
      </DrillDownSheet>,
    );
    const refreshBtn = screen.getByLabelText("Refresh");
    await user.click(refreshBtn);
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("does not render refresh button when onRefresh is undefined", () => {
    render(
      <DrillDownSheet open onClose={onClose} title="No Refresh">
        <p>Body</p>
      </DrillDownSheet>,
    );
    expect(screen.queryByLabelText("Refresh")).not.toBeInTheDocument();
  });
});
