import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { SectionNav, SECTION_IDS } from "@/components/section-nav";

// Mock scrollIntoView
const mockScrollIntoView = jest.fn();
window.HTMLElement.prototype.scrollIntoView = mockScrollIntoView;

beforeEach(() => {
  mockScrollIntoView.mockClear();
});

test("renders all section pills", () => {
  render(<SectionNav />);
  for (const section of SECTION_IDS) {
    expect(screen.getByText(section.label)).toBeInTheDocument();
  }
});

test("clicking a pill calls scrollIntoView on the target element", () => {
  // Create a target element in the DOM
  const target = document.createElement("div");
  target.id = SECTION_IDS[0].id;
  document.body.appendChild(target);

  render(<SectionNav />);
  fireEvent.click(screen.getByText(SECTION_IDS[0].label));
  expect(target.scrollIntoView).toHaveBeenCalledWith({
    behavior: "smooth",
    block: "start",
  });

  document.body.removeChild(target);
});
