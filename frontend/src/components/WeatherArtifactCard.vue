<script setup lang="ts">
import type { WeatherArtifact } from "../types";

defineProps<{
  artifact: WeatherArtifact;
}>();
</script>

<template>
  <section class="weather-card" aria-label="天气卡片">
    <div class="weather-card__header">
      <div>
        <div class="weather-card__eyebrow">天气概览</div>
        <h3 class="weather-card__city">{{ artifact.data.city }}</h3>
        <p class="weather-card__meta">
          {{ artifact.data.relative_day_label }} · {{ artifact.data.forecast_date }} ·
          {{ artifact.data.weekday_label }}
        </p>
      </div>
      <div class="weather-card__source">
        <span>来源</span>
        <a
          v-if="artifact.data.source_url"
          :href="artifact.data.source_url"
          target="_blank"
          rel="noreferrer"
        >
          {{ artifact.data.source_name }}
        </a>
        <span v-else>{{ artifact.data.source_name }}</span>
      </div>
    </div>

    <div class="weather-card__hero">
      <div class="weather-card__temperature">
        <span v-if="artifact.data.current_temp_c !== null && artifact.data.current_temp_c !== undefined">
          {{ artifact.data.current_temp_c }}°
        </span>
        <span v-else>
          {{ artifact.data.temp_low_c ?? "--" }}° / {{ artifact.data.temp_high_c ?? "--" }}°
        </span>
      </div>
      <div class="weather-card__summary">
        <p class="weather-card__condition">{{ artifact.data.summary }}</p>
        <p v-if="artifact.data.feels_like_c !== null && artifact.data.feels_like_c !== undefined">
          体感 {{ artifact.data.feels_like_c }}°
        </p>
      </div>
    </div>

    <div class="weather-card__grid">
      <div class="weather-card__field">
        <span class="weather-card__label">温度</span>
        <strong>{{ artifact.data.temp_low_c ?? "--" }}° ~ {{ artifact.data.temp_high_c ?? "--" }}°</strong>
      </div>
      <div class="weather-card__field">
        <span class="weather-card__label">风力</span>
        <strong>{{ artifact.data.wind_text || "暂无" }}</strong>
      </div>
      <div class="weather-card__field">
        <span class="weather-card__label">空气质量</span>
        <strong>{{ artifact.data.air_quality || "暂无" }}</strong>
      </div>
      <div class="weather-card__field">
        <span class="weather-card__label">完整度</span>
        <strong>
          {{ artifact.data.completeness?.has_forecast ? "已含预报" : "仅当前" }}
        </strong>
      </div>
    </div>

    <div v-if="artifact.data.forecast_items?.length" class="weather-card__forecast">
      <div class="weather-card__forecast-title">未来预报</div>
      <div class="weather-card__forecast-list">
        <article
          v-for="item in artifact.data.forecast_items"
          :key="`${item.date}-${item.weekday_label}`"
          class="weather-card__forecast-item"
        >
          <p class="weather-card__forecast-day">{{ item.relative_day_label }}</p>
          <p class="weather-card__forecast-date">{{ item.date }}</p>
          <p class="weather-card__forecast-condition">{{ item.condition }}</p>
          <p class="weather-card__forecast-temp">
            {{ item.temp_low_c ?? "--" }}° / {{ item.temp_high_c ?? "--" }}°
          </p>
        </article>
      </div>
    </div>
  </section>
</template>

<style scoped>
.weather-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px;
  border-radius: 22px;
  background:
    radial-gradient(circle at top right, rgba(179, 0, 0, 0.16), transparent 44%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(255, 247, 247, 0.94));
  border: 1px solid rgba(179, 0, 0, 0.14);
  box-shadow: 0 18px 42px -26px rgba(179, 0, 0, 0.34);
  color: #111827;
}

.weather-card__header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.weather-card__eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: #b30000;
}

.weather-card__city {
  margin: 6px 0 0;
  font-size: 24px;
  font-weight: 800;
  line-height: 1.1;
}

.weather-card__meta {
  margin: 6px 0 0;
  font-size: 12px;
  color: rgba(17, 24, 39, 0.62);
}

.weather-card__source {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  font-size: 12px;
  color: rgba(17, 24, 39, 0.58);
}

.weather-card__source a {
  color: #b30000;
  text-decoration: none;
}

.weather-card__hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(179, 0, 0, 0.06);
}

.weather-card__temperature {
  font-size: 44px;
  font-weight: 900;
  letter-spacing: -0.04em;
  color: #7f1d1d;
}

.weather-card__summary {
  text-align: right;
  color: #374151;
}

.weather-card__condition {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
}

.weather-card__summary p:last-child {
  margin: 4px 0 0;
  font-size: 13px;
}

.weather-card__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.weather-card__field {
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(15, 23, 42, 0.06);
}

.weather-card__label {
  display: block;
  margin-bottom: 6px;
  font-size: 11px;
  color: rgba(17, 24, 39, 0.52);
  text-transform: uppercase;
  letter-spacing: 0.16em;
}

.weather-card__field strong {
  font-size: 14px;
  font-weight: 700;
  color: #111827;
}

.weather-card__forecast {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.weather-card__forecast-title {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgba(127, 29, 29, 0.82);
}

.weather-card__forecast-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.weather-card__forecast-item {
  padding: 12px;
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.03);
  border: 1px solid rgba(15, 23, 42, 0.04);
}

.weather-card__forecast-item p {
  margin: 0;
}

.weather-card__forecast-day {
  font-size: 12px;
  font-weight: 700;
  color: #7f1d1d;
}

.weather-card__forecast-date {
  margin-top: 4px !important;
  font-size: 11px;
  color: rgba(17, 24, 39, 0.58);
}

.weather-card__forecast-condition {
  margin-top: 10px !important;
  font-size: 14px;
  font-weight: 700;
}

.weather-card__forecast-temp {
  margin-top: 4px !important;
  font-size: 13px;
  color: rgba(17, 24, 39, 0.72);
}
</style>
