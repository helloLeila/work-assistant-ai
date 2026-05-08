<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";

import { message as antMessage } from "ant-design-vue";
import {
  PlusOutlined,
  EditOutlined,
  SendOutlined,
} from "@ant-design/icons-vue";

import AppSidebar from "../components/AppSidebar.vue";
import ChatMessageBubble from "../components/ChatMessageBubble.vue";
import QuickActionCards from "../components/QuickActionCards.vue";
import StatBadge from "../components/StatBadge.vue";
import { openChatStream } from "../composables/useChatStream";
import { requestJson } from "../lib/api";
import { sessionState } from "../stores/session";
import type {
  ChatMessage,
  HistorySession,
  QuickAction,
  SourceFile,
} from "../types";

const quickActions: QuickAction[] = [
  {
    key: "知识库",
    title: "查询企业制度",
    description: "检索上传到知识库中的规章、FAQ 和操作手册。",
    prompt: "帮我总结公司的差旅报销标准，并列出关键限制条件。",
  },
  {
    key: "薪酬",
    title: "查询薪酬信息",
    description: "按用户角色自动控制可见薪酬范围和字段。",
    prompt: "请查询我本月的薪酬总包。",
  },
  {
    key: "个人信息",
    title: "查看年假与合同",
    description: "自动返回可读信息，并对敏感字段执行脱敏。",
    prompt: "帮我查看我的合同到期日、剩余年假和部门信息。",
  },
  {
    key: "商旅代办",
    title: "发起出行申请",
    description: "从自然语言中抽取出发地、日期、人数和舱位。",
    prompt: "下周二帮我预订上海到深圳的商务舱，2位乘客。",
  },
];

const historySessions = ref<HistorySession[]>([]);
const currentSessionId = ref(`session-${crypto.randomUUID()}`);
const currentTitle = ref("新会话");
const messages = ref<ChatMessage[]>([]);
const composer = ref("");
const streaming = ref(false);
const errorMessage = ref("");
const scrollAreaRef = ref<HTMLDivElement | null>(null);
let streamHandle: EventSource | null = null;

function scrollChatToBottom(): void {
  // nextTick 等 DOM 更新完再滚，否则取到的 scrollHeight 是更新前的旧值。
  void nextTick(() => {
    const el = scrollAreaRef.value;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  });
}

// 任意一条消息内容变化（包括 token 流式追加）都把容器滚到最下面。
watch(
  () => messages.value.map((item) => item.content).join("|"),
  () => scrollChatToBottom(),
);

const statusCards = computed(() => [
  { label: "当前用户", value: sessionState.user?.name ?? "-" },
  { label: "角色", value: sessionState.user?.role ?? "-" },
  { label: "部门", value: sessionState.user?.department ?? "-" },
  { label: "能力", value: "知识 / 薪酬 / 个人 / 商旅" },
]);

function nowString(): string {
  return new Date().toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function loadHistory(): Promise<void> {
  try {
    const payload = await requestJson<{ items: HistorySession[]; total: number }>(
      "/chat/history?page=1&page_size=20",
    );
    historySessions.value = payload.items;
  } catch (error) {
    // 历史加载失败不应阻塞会话发送，仅在控制台记录。
    console.warn("加载历史会话失败：", error);
  }
}

function selectSession(session: HistorySession): void {
  currentSessionId.value = session.session_id;
  currentTitle.value = session.title;
  messages.value = session.turns.map((turn, index) => ({
    id: `${session.session_id}-${index}`,
    role: turn.role,
    content: turn.content,
    createdAt: turn.created_at,
    sources: turn.sources,
  }));
}

async function deleteCurrentSession(sessionId: string): Promise<void> {
  await requestJson(`/chat/session/${sessionId}`, { method: "DELETE" });
  if (currentSessionId.value === sessionId) {
    startNewSession();
  }
  await loadHistory();
}

function startNewSession(): void {
  // 清空当前对话，给一个新 session_id；后端会在用户发第一条消息时才真正创建会话。
  streamHandle?.close();
  streamHandle = null;
  streaming.value = false;
  errorMessage.value = "";
  composer.value = "";
  currentSessionId.value = `session-${crypto.randomUUID()}`;
  currentTitle.value = "新会话";
  messages.value = [];
}

async function renameSession(sessionId: string, nextTitle: string): Promise<void> {
  const trimmed = nextTitle.trim();
  if (!trimmed) {
    return;
  }
  try {
    await requestJson(`/chat/session/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify({ title: trimmed }),
    });
    // 本地同步更新，避免等接口轮询。
    const session = historySessions.value.find((item) => item.session_id === sessionId);
    if (session) {
      session.title = trimmed;
    }
    if (currentSessionId.value === sessionId) {
      currentTitle.value = trimmed;
    }
  } catch (error) {
    errorMessage.value = `重命名失败：${(error as Error).message}`;
  }
}

function appendAssistantMessage(): ChatMessage {
  const message: ChatMessage = {
    id: `assistant-${crypto.randomUUID()}`,
    role: "assistant",
    content: "",
    createdAt: nowString(),
    sources: [],
    thinking: "",
    // 一开始就标记 isThinking=true，配合 thinkingStartAt 计时。
    // 等收到第一个真正的 token 时再把 isThinking 切成 false 并落定 thinkingEndAt。
    isThinking: true,
    thinkingStartAt: Date.now(),
    // 豆包行为：思考阶段默认展开，便于实时围观；
    // 当第一段正式 token 抵达时（onToken 里），自动收起。
    thinkingExpanded: true,
    // 标记 SSE 流进行中，用于在气泡尾部显示闪烁光标，让用户能看到"还在生成"。
    isStreaming: true,
  };
  messages.value.push(message);
  // push 后必须从数组里再取出来，拿到的才是 Vue 包过的 reactive proxy；
  // 直接用 push 之前的原始引用做 mutation 不会触发 UI 重新渲染。
  return messages.value[messages.value.length - 1];
}

async function sendMessage(input?: unknown): Promise<void> {
  // 兼容三种调用：按钮 @click（传入 MouseEvent）、Enter 键、QuickAction 的字符串。
  const raw = typeof input === "string" ? input : composer.value;
  const query = raw.trim();
  if (!query || streaming.value) {
    return;
  }

  errorMessage.value = "";
  currentTitle.value = query.slice(0, 24);
  messages.value.push({
    id: `user-${crypto.randomUUID()}`,
    role: "user",
    content: query,
    createdAt: nowString(),
  });
  composer.value = "";
  streaming.value = true;

  const assistantMessage = appendAssistantMessage();

  streamHandle?.close();
  streamHandle = openChatStream(currentSessionId.value, query, {
    onToken(token) {
      // 第一个真正的回答 token 抵达时，思考阶段结束：
      // 1. 计时停止（thinkingEndAt 落定）
      // 2. 折叠思考块（豆包行为：进入正式回答后自动收起，避免抢占焦点）
      if (assistantMessage.isThinking) {
        assistantMessage.isThinking = false;
        assistantMessage.thinkingEndAt = Date.now();
        assistantMessage.thinkingExpanded = false;
      }
      assistantMessage.content += token;
    },
    onThinking(chunk) {
      assistantMessage.thinking = (assistantMessage.thinking ?? "") + chunk;
    },
    onSources(sources: SourceFile[]) {
      assistantMessage.sources = sources;
    },
    async onDone() {
      // 兜底：极端情况下整轮没有正式 token（例如纯 thinking 后流就结束了），
      // 也要把 isThinking 收尾，避免气泡一直转圈。
      if (assistantMessage.isThinking) {
        assistantMessage.isThinking = false;
        assistantMessage.thinkingEndAt = Date.now();
      }
      assistantMessage.isStreaming = false;
      streaming.value = false;
      await loadHistory();
    },
    onError(message) {
      assistantMessage.isThinking = false;
      assistantMessage.isStreaming = false;
      streaming.value = false;
      errorMessage.value = message;
    },
  });
}

// 重命名当前会话：在模板里挂一个 <a-modal>，这里只控制开关与草稿。
const renameModalOpen = ref(false);
const renameDraft = ref("");

// 是否显示模型的 <think> 思考过程：默认显示。
// 关闭后前端给对话区根节点加一个 `hide-thinking` class，
// 全局 CSS 把 `.hide-thinking .think-block { display: none }` 隐藏掉。
const showThinking = ref(true);

function onRenameCurrent(): void {
  const exists = historySessions.value.some(
    (item) => item.session_id === currentSessionId.value,
  );
  if (!exists) {
    antMessage.warning("新会话还没保存，至少发一条消息后才能重命名");
    return;
  }
  renameDraft.value = currentTitle.value;
  renameModalOpen.value = true;
}

async function confirmRename(): Promise<void> {
  await renameSession(currentSessionId.value, renameDraft.value);
  renameModalOpen.value = false;
}

function handleComposerKeydown(event: KeyboardEvent): void {
  // 兼容多数聊天产品的快捷键：Enter 发送，Shift+Enter 换行。
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    void sendMessage();
  }
}

onMounted(async () => {
  await loadHistory();
  if (historySessions.value.length) {
    selectSession(historySessions.value[0]);
  }
});
</script>

<template>
  <a-layout class="workspace-layout">
    <a-layout-sider :width="300" class="workspace-sider">
      <AppSidebar
        :sessions="historySessions"
        :current-session-id="currentSessionId"
        @new-session="startNewSession"
        @select-session="selectSession"
        @delete-session="deleteCurrentSession"
        @rename-session="renameSession"
      />
    </a-layout-sider>

    <a-layout-content class="workspace-main">
      <div class="workspace-stack">
        <!-- 顶部：标题 + 新建会话 + 状态卡片 -->
        <a-card :bordered="false" class="header-card">
          <div class="header-card__row">
            <div class="header-card__left">
              <div class="header-card__top">
                <a-typography-text type="secondary" class="header-card__eyebrow">
                  智能工作台
                </a-typography-text>
                <a-button type="primary" @click="startNewSession">
                  <template #icon><PlusOutlined /></template>
                  新建会话
                </a-button>
              </div>
              <h1 class="header-card__title">
                <span>{{ currentTitle }}</span>
                <a-tooltip v-if="messages.length" title="重命名当前会话">
                  <a-button
                    type="text"
                    shape="circle"
                    @click="onRenameCurrent"
                  >
                    <template #icon><EditOutlined /></template>
                  </a-button>
                </a-tooltip>
              </h1>
              <a-typography-paragraph type="secondary" class="header-card__desc">
                在一个统一入口中完成知识检索、薪酬查询、个人信息查询与商旅代办。
              </a-typography-paragraph>
            </div>

            <div class="status-grid">
              <StatBadge
                v-for="item in statusCards"
                :key="item.label"
                :label="item.label"
                :value="item.value"
              />
            </div>
          </div>
        </a-card>

        <!-- 快捷模板 -->
        <QuickActionCards :actions="quickActions" @pick="sendMessage" />

        <!-- 对话区 -->
        <a-card :bordered="false" class="chat-card">
          <div class="chat-card__header">
            <div>
              <a-typography-text type="secondary" class="chat-card__eyebrow">
                对话区
              </a-typography-text>
              <h2 class="chat-card__title">与企业智能办公助手交流</h2>
            </div>
            <a-tag :color="streaming ? 'processing' : 'success'">
              {{ streaming ? "处理中" : "空闲" }}
            </a-tag>
          </div>

          <div
            ref="scrollAreaRef"
            class="chat-scroll-area"
            :class="{ 'hide-thinking': !showThinking }"
          >
            <a-empty
              v-if="!messages.length"
              description="这里是新会话。试试上面的快捷模板，或者直接在下方输入框开始提问～"
              class="chat-empty"
            />

            <ChatMessageBubble
              v-for="msg in messages"
              :key="msg.id"
              :message="msg"
            />

            <!--
              旧的全局 "正在生成回复" 转圈框已经移除，
              改由 ChatMessageBubble 顶部的"思考中… X.Xs"折叠块显示状态。
            -->

          </div>

          <div class="composer">
            <div class="composer__header">
              <a-typography-text strong class="composer__label">
                输入你的问题
              </a-typography-text>
              <a-tooltip
                title="开启后，助手回复中如有思考过程会以折叠块展示；关闭则只看最终答案。"
              >
                <span class="composer__toggle">
                  <a-switch
                    v-model:checked="showThinking"
                    size="small"
                    checked-children="思考"
                    un-checked-children="隐藏"
                  />
                  <span class="composer__toggle-label">显示思考过程</span>
                </span>
              </a-tooltip>
            </div>
            <a-textarea
              v-model:value="composer"
              :rows="4"
              :auto-size="{ minRows: 4, maxRows: 8 }"
              placeholder="例如：帮我总结公司的差旅报销制度。（Enter 发送，Shift+Enter 换行）"
              @keydown="handleComposerKeydown"
            />

            <div class="composer__footer">
              <a-typography-text v-if="errorMessage" type="danger">
                {{ errorMessage }}
              </a-typography-text>
              <a-typography-text v-else type="secondary">
                回答将按流式方式逐段返回，并在末尾附上引用来源。
              </a-typography-text>
              <a-button
                type="primary"
                size="large"
                :loading="streaming"
                @click="sendMessage"
              >
                <template #icon><SendOutlined /></template>
                发送
              </a-button>
            </div>
          </div>
        </a-card>
      </div>

      <!-- 重命名弹窗 -->
      <a-modal
        v-model:open="renameModalOpen"
        title="重命名当前会话"
        :ok-text="'保存'"
        :cancel-text="'取消'"
        centered
        @ok="confirmRename"
      >
        <a-input
          v-model:value="renameDraft"
          :maxlength="60"
          placeholder="请输入新的会话标题"
          @press-enter="confirmRename"
        />
      </a-modal>
    </a-layout-content>
  </a-layout>
</template>

<style scoped>
.workspace-layout {
  min-height: 100vh;
  background: #f8fafc;
}

/* sider 本身 sticky 在视口顶部，自身高度 100vh，让侧边栏永远可见。
   antd 的 a-layout 是 flex row 容器，sticky 在 flex item 上完全可用。 */
.workspace-sider {
  background: transparent !important;
  position: sticky !important;
  top: 0;
  align-self: flex-start;
  height: 100vh !important;
}

.workspace-sider :deep(.ant-layout-sider-children) {
  display: flex;
  height: 100%;
}

.workspace-main {
  padding: 24px 32px;
}

.workspace-stack {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* Header */
.header-card :deep(.ant-card-body) {
  padding: 24px 28px;
}

.header-card__row {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

@media (min-width: 1280px) {
  .header-card__row {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
  }
}

.header-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.header-card__eyebrow {
  font-size: 11px;
  letter-spacing: 0.32em;
  text-transform: uppercase;
  color: #b30000 !important;
}

.header-card__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 14px 0 6px;
  font-size: 28px;
  font-weight: 800;
  color: #1f2937;
}

.header-card__desc {
  margin: 0 !important;
  max-width: 720px;
  line-height: 1.7;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  width: 100%;
}

@media (min-width: 1280px) {
  .status-grid {
    width: 440px;
  }
}

/* Chat card */
.chat-card :deep(.ant-card-body) {
  padding: 20px 24px 24px;
}

.chat-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 16px;
  border-bottom: 1px solid #fee2e2;
  margin-bottom: 16px;
}

.chat-card__eyebrow {
  font-size: 11px;
  letter-spacing: 0.28em;
  text-transform: uppercase;
  color: #b30000 !important;
}

.chat-card__title {
  margin: 6px 0 0;
  font-size: 18px;
  font-weight: 700;
  color: #1f2937;
}

.chat-empty {
  margin: 24px 0;
}

.chat-typing {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
}

/* Composer */
.composer {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #fee2e2;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.composer__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.composer__label {
  color: #334155;
}

.composer__toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.composer__toggle-label {
  font-size: 12px;
  color: #64748b;
}

.composer__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 4px;
}
</style>
