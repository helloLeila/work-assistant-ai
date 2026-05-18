<script setup lang="ts">
import { computed } from "vue";

import type { DateArtifact } from "../types";

const props = defineProps<{
  artifact: DateArtifact;
}>();

const timezoneLabel = computed(() => {
  if (props.artifact.data.timezone === "Asia/Shanghai") {
    return "北京时间";
  }
  return "当地时间";
});
</script>

<template>
  <section class="date-card" aria-label="日期卡片">
    <div class="date-card__eyebrow">日期信息</div>
    <div class="date-card__body">
      <div class="date-card__icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="22" height="22">
          <path
            fill="currentColor"
            d="M7 2a1 1 0 0 1 1 1v1h8V3a1 1 0 1 1 2 0v1h1.5A2.5 2.5 0 0 1 22 6.5v12A2.5 2.5 0 0 1 19.5 21h-15A2.5 2.5 0 0 1 2 18.5v-12A2.5 2.5 0 0 1 4.5 4H6V3a1 1 0 0 1 1-1Zm12 8H5v8.5c0 .28.22.5.5.5h15a.5.5 0 0 0 .5-.5V10Zm-1.5-4h-15a.5.5 0 0 0-.5.5V8h16V6.5a.5.5 0 0 0-.5-.5Z"
          />
        </svg>
      </div>
      <div class="date-card__content">
        <p class="date-card__title">{{ artifact.data.title }}</p>
        <p class="date-card__date">{{ artifact.data.date_text }}</p>
        <p class="date-card__weekday">{{ artifact.data.weekday_label }}</p>
      </div>
    </div>
    <div class="date-card__footer">
      <span class="date-card__timezone">{{ timezoneLabel }}</span>
    </div>
  </section>
</template>

<style scoped>
.date-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 18px;
  border-radius: 20px;
  background:
    radial-gradient(circle at top left, rgba(179, 0, 0, 0.14), transparent 55%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(255, 247, 247, 0.94));
  border: 1px solid rgba(179, 0, 0, 0.12);
  box-shadow: 0 14px 32px -22px rgba(179, 0, 0, 0.28);
  color: #1f2937;
}

.date-card__eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: #b30000;
}

.date-card__body {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.date-card__icon {
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: 14px;
  color: #b30000;
  background: rgba(179, 0, 0, 0.08);
}

.date-card__content {
  min-width: 0;
}

.date-card__title {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: #7f1d1d;
}

.date-card__date {
  margin: 4px 0 0;
  font-size: 24px;
  font-weight: 800;
  letter-spacing: 0.02em;
  color: #111827;
}

.date-card__weekday {
  margin: 4px 0 0;
  font-size: 13px;
  color: #4b5563;
}

.date-card__footer {
  display: flex;
  justify-content: flex-end;
}

.date-card__timezone {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.05);
  font-size: 11px;
  color: rgba(15, 23, 42, 0.66);
  font-variant-numeric: tabular-nums;
}
</style>
