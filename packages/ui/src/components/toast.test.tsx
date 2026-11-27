import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider, useToast } from "./toast";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function Trigger({ tone }: { tone?: "error" | "success" }) {
  const { push } = useToast();
  return (
    <button type="button" onClick={() => push({ title: "Board uploaded", tone, duration: 1000 })}>
      fire
    </button>
  );
}

describe("toasts", () => {
  it("announces, dismisses on click, and closes itself after its duration", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByText("fire"));
    expect(screen.getByRole("status").textContent).toContain("Board uploaded");
    fireEvent.click(screen.getByRole("button", { name: "Dismiss notification" }));
    expect(screen.queryByRole("status")).toBeNull();

    fireEvent.click(screen.getByText("fire"));
    act(() => vi.advanceTimersByTime(1100));
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("uses an alert role for errors and keeps at most three", () => {
    render(
      <ToastProvider>
        <Trigger tone="error" />
      </ToastProvider>,
    );
    for (let i = 0; i < 5; i++) fireEvent.click(screen.getByText("fire"));
    expect(screen.getAllByRole("alert")).toHaveLength(3);
  });
});
