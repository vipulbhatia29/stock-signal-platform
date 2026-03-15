import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StatTile } from "@/components/stat-tile";

test("renders label and value", () => {
  render(<StatTile label="Portfolio Value" value="$124,830" />);
  expect(screen.getByText("Portfolio Value")).toBeInTheDocument();
  expect(screen.getByText("$124,830")).toBeInTheDocument();
});

test("renders children instead of value when provided", () => {
  render(
    <StatTile label="Signals">
      <span>custom content</span>
    </StatTile>
  );
  expect(screen.getByText("custom content")).toBeInTheDocument();
});

test("calls onClick when clicked", async () => {
  const onClick = jest.fn();
  render(<StatTile label="Test" value="123" onClick={onClick} />);
  // Click the label text — it is inside the clickable div
  await userEvent.click(screen.getByText("Test"));
  expect(onClick).toHaveBeenCalledTimes(1);
});
