<script setup lang="ts">
defineProps<{
  label: string;
  value: string;
}>();
</script>

<template>
  <a-card :bordered="false" size="small" class="stat-badge">
    <p class="stat-badge__label">{{ label }}</p>
    <p class="stat-badge__value">{{ value }}</p>
  </a-card>
</template>

<style scoped>
.stat-badge {
  border-radius: 16px !important;
  background: linear-gradient(135deg, #fff 0%, #fff5f7 100%) !important;
  border: 1px solid #fee2e2 !important;
}

.stat-badge :deep(.ant-card-body) {
  padding: 12px 16px;
}

.stat-badge__label {
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: #b30000;
}

.stat-badge__value {
  margin: 4px 0 0;
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}
</style>
