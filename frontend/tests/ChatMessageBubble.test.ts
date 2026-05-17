// @vitest-environment jsdom

import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import ChatMessageBubble from "../src/components/ChatMessageBubble.vue";

describe("ChatMessageBubble", () => {
  it("renders artifact cards for assistant messages", () => {
    const wrapper = mount(ChatMessageBubble, {
      props: {
        message: {
          id: "assistant-1",
          role: "assistant",
          content: "今天是 2026年05月17日，星期日。",
          createdAt: "12:00",
          artifacts: [
            {
              kind: "date_card",
              version: 1,
              data: {
                title: "今天",
                date_text: "2026年05月17日",
                weekday_label: "星期日",
                timezone: "Asia/Shanghai",
              },
            },
          ],
        },
      },
    });

    expect(wrapper.text()).toContain("2026年05月17日");
    expect(wrapper.text()).toContain("星期日");
    expect(wrapper.text()).toContain("Asia/Shanghai");
  });
});
