<script setup lang="ts">
import type { QuickAction } from "../types";

defineProps<{
  actions: QuickAction[];
}>();

const emit = defineEmits<{
  pick: [prompt: string];
}>();
</script>

<template>
  <a-row :gutter="[16, 16]">
    <a-col
      v-for="action in actions"
      :key="action.key"
      :xs="24"
      :md="12"
      :xl="6"
    >
      <!--
        作用域插槽：父组件可拿到 action 自定义渲染。
        默认渲染 = 玫红色徽章 + 标题 + 描述。
        想换成图标卡片、彩色卡片、带 badge 的卡片，外面传 <template #default="{ action, pick }"> 即可。
      -->
      <slot :action="action" :pick="() => emit('pick', action.prompt)">
        <a-card
          hoverable
          :bordered="false"
          class="quick-card"
          @click="emit('pick', action.prompt)"
        >
          <p class="quick-card__eyebrow">{{ action.key }}</p>
          <p class="quick-card__title">{{ action.title }}</p>
          <p class="quick-card__desc">{{ action.description }}</p>
        </a-card>
      </slot>
    </a-col>
  </a-row>
</template>

<style scoped>
.quick-card {
  height: 100%;
  border-radius: 24px !important;
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}

.quick-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 18px 36px -16px rgba(190, 18, 60, 0.25);
}

.quick-card :deep(.ant-card-body) {
  padding: 20px 22px;
}

.quick-card__eyebrow {
  font-size: 11px;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: #b30000;
  margin: 0;
}

.quick-card__title {
  margin: 12px 0 6px;
  font-size: 17px;
  font-weight: 700;
  color: #0f172a;
}

.quick-card__desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: #475569;
}
</style>
