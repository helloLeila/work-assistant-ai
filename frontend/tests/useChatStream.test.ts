// @vitest-environment jsdom

import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/stores/session", () => ({
  sessionState: { accessToken: "" },
}));

class FakeEventSource {
  static lastInstance: FakeEventSource | null = null;

  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  closed = false;

  constructor(public url: string) {
    FakeEventSource.lastInstance = this;
  }

  close(): void {
    this.closed = true;
  }
}

describe("openChatStream", () => {
  const originalEventSource = globalThis.EventSource;

  beforeEach(() => {
    globalThis.EventSource = FakeEventSource as unknown as typeof EventSource;
    FakeEventSource.lastInstance = null;
  });

  afterEach(() => {
    globalThis.EventSource = originalEventSource;
  });

  it("dispatches artifact events to the caller", async () => {
    const handlers = {
      onToken: vi.fn(),
      onSources: vi.fn(),
      onDone: vi.fn(),
      onError: vi.fn(),
      onArtifact: vi.fn(),
    };

    const { openChatStream } = await import("../src/composables/useChatStream");
    const { sessionState } = await import("../src/stores/session");
    sessionState.accessToken = "access-token";

    openChatStream("session-1", "今天几号", handlers as never);

    FakeEventSource.lastInstance?.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({
          type: "artifact",
          artifact: { kind: "date_card", version: 1, data: { title: "今天" } },
        }),
      }),
    );

    expect(handlers.onArtifact).toHaveBeenCalledWith({
      kind: "date_card",
      version: 1,
      data: { title: "今天" },
    });
  });
});
