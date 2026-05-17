// @vitest-environment jsdom

import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import WeatherArtifactCard from "../src/components/WeatherArtifactCard.vue";

describe("WeatherArtifactCard", () => {
  it("renders current weather and forecast rows", () => {
    const wrapper = mount(WeatherArtifactCard, {
      props: {
        artifact: {
          kind: "weather_card",
          version: 1,
          data: {
            city: "深圳",
            relative_day_label: "今天",
            forecast_date: "2026-05-17",
            weekday_label: "星期日",
            summary: "多云",
            current_temp_c: 26,
            temp_low_c: 20,
            temp_high_c: 31,
            feels_like_c: 28,
            wind_text: "南风3级",
            air_quality: "优",
            source_name: "天气网",
            source_url: "https://weather.example.com/shenzhen",
            forecast_items: [
              {
                date: "2026-05-18",
                weekday_label: "星期一",
                relative_day_label: "明天",
                condition: "小雨",
                temp_low_c: 22,
                temp_high_c: 29,
              },
            ],
            completeness: {
              has_current: true,
              has_forecast: true,
              missing_fields: [],
            },
          },
        },
      },
    });

    expect(wrapper.text()).toContain("深圳");
    expect(wrapper.text()).toContain("26");
    expect(wrapper.text()).toContain("31");
    expect(wrapper.text()).toContain("南风3级");
    expect(wrapper.text()).toContain("优");
    expect(wrapper.text()).toContain("明天");
    expect(wrapper.text()).toContain("小雨");
  });
});
