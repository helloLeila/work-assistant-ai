// @vitest-environment jsdom

import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import DateArtifactCard from "../src/components/DateArtifactCard.vue";

describe("DateArtifactCard", () => {
  it("renders the local date summary", () => {
    const wrapper = mount(DateArtifactCard, {
      props: {
        artifact: {
          kind: "date_card",
          version: 1,
          data: {
            title: "今天",
            date_text: "2026年05月17日",
            weekday_label: "星期日",
            timezone: "Asia/Shanghai",
          },
        },
      },
    });

    expect(wrapper.text()).toContain("今天");
    expect(wrapper.text()).toContain("2026年05月17日");
    expect(wrapper.text()).toContain("星期日");
    expect(wrapper.text()).toContain("北京时间");
  });
});
