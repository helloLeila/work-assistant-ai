<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
} from "@ant-design/icons-vue";

import { sessionState } from "../stores/session";
import type { HistorySession } from "../types";

const props = defineProps<{
  sessions: HistorySession[];
  currentSessionId?: string;
}>();

const emit = defineEmits<{
  newSession: [];
  selectSession: [session: HistorySession];
  deleteSession: [sessionId: string];
  renameSession: [sessionId: string, title: string];
}>();

const route = useRoute();
// 行内重命名状态：仅记录"哪一条在编辑 + 草稿值"。
const editingId = ref<string | null>(null);
const editingDraft = ref("");

const navItems = computed(() => {
  const items = [{ to: "/workspace", label: "工作台", hint: "会话、问答与流程处理" }];

  if (sessionState.user?.role === "hr_admin" || sessionState.user?.role === "knowledge_admin") {
    items.push({ to: "/knowledge", label: "知识库管理", hint: "文档上传、入库与清理" });
  }

  return items;
});

// 至少 5 个槽位（少于 5 条历史时用占位条补齐，让卡片高度看起来稳定）。
const placeholderCount = computed(() => Math.max(0, 5 - props.sessions.length));

function startEditing(session: HistorySession, event: Event): void {
  event.stopPropagation();
  editingId.value = session.session_id;
  editingDraft.value = session.title;
}

function commitEditing(): void {
  if (editingId.value && editingDraft.value.trim()) {
    emit("renameSession", editingId.value, editingDraft.value.trim());
  }
  editingId.value = null;
  editingDraft.value = "";
}

function cancelEditing(): void {
  editingId.value = null;
  editingDraft.value = "";
}

</script>

<template>
  <aside class="sidebar-shell">
    <div class="space-y-7">
      <!-- 品牌区 -->
      <div class="brand-card">
        <div class="brand-logo">T</div>
        <div>
          <p class="brand-eyebrow">TongTong AI</p>
          <p class="brand-title">企业智能办公助手</p>
        </div>
      </div>

      <p class="intro-text">
        支持知识检索、薪酬查询、个人信息查询和商旅代办，
        在同一条对话流里完成权限控制与结构化处理。
      </p>

      <!-- 导航 -->
      <nav class="space-y-2">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="nav-link"
          :class="{ 'nav-link--active': route.path === item.to }"
        >
          <p class="nav-link__label">{{ item.label }}</p>
          <p class="nav-link__hint">{{ item.hint }}</p>
        </RouterLink>
      </nav>

      <!-- 历史会话 -->
      <section class="history-card">
        <div class="history-card__header">
          <p class="history-card__title">最近会话</p>
          <a-button
            type="primary"
            size="small"
            shape="round"
            ghost
            @click="emit('newSession')"
          >
            <template #icon><PlusOutlined /></template>
            新建
          </a-button>
        </div>

        <div class="history-list">
          <div
            v-for="session in sessions"
            :key="session.session_id"
            class="history-item group"
            :class="{ 'history-item--active': currentSessionId === session.session_id }"
          >
            <!-- 编辑态：行内输入 -->
            <div
              v-if="editingId === session.session_id"
              class="history-item__editor"
            >
              <a-input
                v-model:value="editingDraft"
                size="small"
                :maxlength="60"
                @press-enter="commitEditing"
                @keydown.esc.prevent="cancelEditing"
              />
              <a-button type="link" size="small" @click="commitEditing">保存</a-button>
              <a-button type="link" size="small" danger @click="cancelEditing">
                取消
              </a-button>
            </div>

            <!-- 展示态 -->
            <button
              v-else
              type="button"
              class="history-item__main"
              @click="emit('selectSession', session)"
            >
              <p class="history-item__title">{{ session.title }}</p>
              <p class="history-item__time">
                {{ session.updated_at.replace('T', ' ').slice(0, 16) }}
              </p>
            </button>

            <div
              v-if="editingId !== session.session_id"
              class="history-item__actions"
            >
              <a-tooltip title="重命名">
                <a-button
                  type="text"
                  size="small"
                  class="action-btn"
                  @click="startEditing(session, $event)"
                >
                  <template #icon><EditOutlined /></template>
                </a-button>
              </a-tooltip>
              <a-tooltip title="删除">
                <a-button
                  type="text"
                  size="small"
                  class="action-btn action-btn--danger"
                  @click.stop="emit('deleteSession', session.session_id)"
                >
                  <template #icon><DeleteOutlined /></template>
                </a-button>
              </a-tooltip>
            </div>
          </div>

          <!-- 占位条：保证至少 5 个视觉槽位 -->
          <div
            v-for="i in placeholderCount"
            :key="`placeholder-${i}`"
            class="history-placeholder"
          >
            <p class="history-placeholder__title">空闲槽位</p>
            <p class="history-placeholder__hint">点击「+ 新建」开启对话</p>
          </div>
        </div>
      </section>
    </div>
  </aside>
</template>

<style scoped>
/* 白底深字配色：底色干净、品牌红 (#b30000) 仅作高亮强调。
   sticky 定位让侧边栏始终在视口里，不会随着右侧内容滚走。 */
.sidebar-shell {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  width: 100%;
  max-width: 300px;
  height: 100%;
  padding: 24px 18px;
  background: #ffffff;
  color: #0f172a;
  border-right: 1px solid #f1f5f9;
  overflow-y: auto;
}

.sidebar-shell::-webkit-scrollbar {
  width: 4px;
}

.sidebar-shell::-webkit-scrollbar-thumb {
  background: rgba(15, 23, 42, 0.12);
  border-radius: 4px;
}

/* 品牌区 */
.brand-card {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: 14px;
  background: #fff5f5;
  border: 1px solid #fee2e2;
}

.brand-logo {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: #b30000;
  color: #fff;
  font-weight: 900;
  font-size: 19px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 6px 18px -8px rgba(179, 0, 0, 0.6);
}

.brand-eyebrow {
  font-size: 10px;
  letter-spacing: 0.3em;
  color: #b30000;
  text-transform: uppercase;
  margin: 0;
  font-weight: 600;
}

.brand-title {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
  margin: 4px 0 0;
}

.intro-text {
  margin: 0;
  padding: 12px 14px;
  border-radius: 14px;
  background: #fafafa;
  border: 1px solid #f1f5f9;
  font-size: 12.5px;
  line-height: 1.7;
  color: #475569;
}

/* 导航 */
.nav-link {
  display: block;
  padding: 12px 14px;
  border-radius: 14px;
  background: #fff;
  border: 1px solid #f1f5f9;
  text-decoration: none;
  transition: background 0.18s ease, border-color 0.18s ease;
}

.nav-link:hover {
  background: #fff5f5;
  border-color: #fee2e2;
}

.nav-link--active {
  background: #fff5f5;
  border-color: #b30000;
  border-left-width: 3px;
  padding-left: 12px;
}

.nav-link__label {
  margin: 0;
  font-size: 13.5px;
  font-weight: 600;
  color: #0f172a;
}

.nav-link__hint {
  margin: 4px 0 0;
  font-size: 11.5px;
  color: #64748b;
}

/* 历史会话 */
.history-card {
  padding: 12px;
  border-radius: 16px;
  background: #fafafa;
  border: 1px solid #f1f5f9;
}

.history-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.history-card__title {
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.28em;
  color: #b30000;
  text-transform: uppercase;
  font-weight: 600;
}

.history-list {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 280px;
  overflow-y: auto;
  padding-right: 4px;
}

.history-list::-webkit-scrollbar {
  width: 4px;
}

.history-list::-webkit-scrollbar-thumb {
  background: rgba(15, 23, 42, 0.12);
  border-radius: 4px;
}

.history-item {
  position: relative;
  border-radius: 12px;
  background: #fff;
  border: 1px solid #f1f5f9;
  transition: background 0.18s ease, border-color 0.18s ease;
}

.history-item:hover {
  background: #fff5f5;
  border-color: #fee2e2;
}

.history-item--active {
  background: #fff5f5;
  border-color: #b30000;
}

.history-item__main {
  display: block;
  width: 100%;
  padding: 10px 12px;
  text-align: left;
  background: transparent;
  border: 0;
  cursor: pointer;
}

.history-item__title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  padding-right: 56px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-item__time {
  margin: 3px 0 0;
  font-size: 11px;
  color: #94a3b8;
}

.history-item__editor {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
}

.history-item__actions {
  position: absolute;
  top: 4px;
  right: 4px;
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.18s ease;
}

.history-item:hover .history-item__actions {
  opacity: 1;
}

.history-placeholder {
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px dashed #e2e8f0;
  background: #fff;
}

.history-placeholder__title {
  margin: 0;
  font-size: 12px;
  color: #94a3b8;
}

.history-placeholder__hint {
  margin: 3px 0 0;
  font-size: 11px;
  color: #cbd5e1;
}

</style>
