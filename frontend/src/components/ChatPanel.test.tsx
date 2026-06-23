import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { ChatPanel } from "./ChatPanel";

describe("ChatPanel", () => {
  it("submits a troubleshooting question", async () => {
    const onAsk = vi.fn().mockResolvedValue(undefined);
    render(
      <ChatPanel
        messages={[]}
        asking={false}
        hasDocuments
        onAsk={onAsk}
        onNewChat={vi.fn()}
        onClearChat={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("Ask a router question"), {
      target: { value: "Why is the LED red?" },
    });
    fireEvent.click(screen.getByLabelText("Send question"));

    expect(onAsk).toHaveBeenCalledWith("Why is the LED red?");
  });
});
