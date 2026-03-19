import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AgentSelector } from "@/components/chat/agent-selector";

test("defaults to stock agent", () => {
  const onChange = jest.fn();
  render(<AgentSelector value="stock" onChange={onChange} />);
  expect(screen.getByText(/Stock Analyst/)).toBeInTheDocument();
});

test("calls onChange when toggled", async () => {
  const onChange = jest.fn();
  render(<AgentSelector value="stock" onChange={onChange} />);
  await userEvent.click(screen.getByText(/General Assistant/));
  expect(onChange).toHaveBeenCalledWith("general");
});
