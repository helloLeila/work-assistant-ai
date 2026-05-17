<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";

import { message as antMessage } from "ant-design-vue";
import {
  PlusOutlined,
  EditOutlined,
  SendOutlined,
  LogoutOutlined,
  DownOutlined,
} from "@ant-design/icons-vue";
import { useRouter } from "vue-router";
import { clearSession } from "../stores/session";

import AppSidebar from "../components/AppSidebar.vue";
import ChatMessageBubble from "../components/ChatMessageBubble.vue";
import QuickActionCards from "../components/QuickActionCards.vue";
import { openChatStream } from "../composables/useChatStream";
import { requestJson } from "../lib/api";
import { sessionState } from "../stores/session";
import type {
  ChatArtifact,
  ChatStep,
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
let scrollTimer: number | null = null;

const HEARTBEAT_DETAILS = [
  "正在整理上下文",
  "正在组织回答结构",
  "正在等待首段输出",
  "正在继续输出内容",
];

function scrollChatToBottom(): void {
  if (scrollTimer !== null) return;
  scrollTimer = window.setTimeout(() => {
    scrollTimer = null;
    // nextTick 等 DOM 更新完再滚，否则取到的 scrollHeight 是更新前的旧值。
    void nextTick(() => {
      const el = scrollAreaRef.value;
      if (el) {
        el.scrollTop = el.scrollHeight;
      }
    });
  }, 80);
}

// 任意一条消息内容变化（包括 token 流式追加）都把容器滚到最下面。
// 只看"末条消息的长度"，避免 map().join() 把所有历史贴拼一遍（O(N) -> O(1)）。
watch(
  () => [messages.value.length, messages.value[messages.value.length - 1]?.content.length ?? 0],
  () => scrollChatToBottom(),
);

const router = useRouter();

// 用户名首字符作头像占位
const userInitial = computed(() => sessionState.user?.name?.slice(0, 1) ?? "?");

function handleLogout(): void {
  clearSession();
  void router.push("/");
}

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
    artifacts: turn.artifacts,
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
    renderedContent: "",
    createdAt: nowString(),
    sources: [],
    thinking: "",
    thinkingPreview: "",
    thinkingFull: "",
    thinkingStats: {
      chars: 0,
      chunks: 0,
      lastUpdatedAt: Date.now(),
    },
    // 一开始就标记 isThinking=true，配合 thinkingStartAt 计时。
    // 等收到第一个真正的 token 时再把 isThinking 切成 false 并落定 thinkingEndAt。
    isThinking: true,
    thinkingStartAt: Date.now(),
    // Claude Code 风格：过程默认以状态轨迹呈现，不自动展开长 thinking 文本。
    thinkingExpanded: false,
    // 标记 SSE 流进行中，用于在气泡尾部显示闪烁光标，让用户能看到"还在生成"。
    isStreaming: true,
    // LangGraph 节点级进度。后端每进入/离开一个节点 push 一条，
    // 前端在思考块里渲染成"⟳ 检索知识库 / ✓ 已筛选相关内容"等步骤列表，
    // 填补"模型还没吐 token"那段冷场（典型 RAG 场景 8-15s）。
    steps: [
      {
        id: "intent",
        label: "理解需求",
        state: "running",
        detail: "正在读取你的问题",
        details: ["正在读取你的问题"],
        startedAt: Date.now(),
      },
    ],
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

  // === Claude Code 风格流式缓冲 ===
  // 上游 token 可能突发抵达；这里把"收到"和"显示"拆开，让正文按稳定节奏吐出。
  // thinking 原文保存在非响应式 buffer，只低频刷新尾部摘录，避免长文本持续重绘。
  let pendingContent = "";
  let contentTimer: number | null = null;
  let streamDone = false;
  let streamFinalized = false;
  let thinkingBuffer = "";
  let thinkingChunks = 0;
  let thinkingPreviewTimer: number | null = null;
  let lastStreamEventAt = Date.now();
  let heartbeatIndex = 0;
  const heartbeatTimer = window.setInterval(() => {
    if (!assistantMessage.isStreaming) return;
    if (Date.now() - lastStreamEventAt < 1800) return;
    const runningStep = [...(assistantMessage.steps ?? [])]
      .reverse()
      .find((step) => step.state === "running");
    const fallbackStep = runningStep ?? {
      id: "working",
      label: "正在处理",
      state: "running" as const,
      startedAt: Date.now(),
    };
    const detail = HEARTBEAT_DETAILS[heartbeatIndex % HEARTBEAT_DETAILS.length];
    heartbeatIndex += 1;
    upsertStep({
      id: fallbackStep.id,
      label: fallbackStep.label,
      state: "running",
      detail,
      synthetic: true,
    });
  }, 900);

  function noteStreamEvent(): void {
    lastStreamEventAt = Date.now();
  }

  function upsertStep(
    patch: Pick<ChatStep, "id" | "label" | "state"> &
      Partial<Pick<ChatStep, "detail" | "synthetic">>,
  ): void {
    const steps = assistantMessage.steps ?? [];
    const existing = steps.find((item) => item.id === patch.id);
    const now = Date.now();
    if (existing) {
      existing.label = patch.label;
      existing.state = patch.state;
      if (patch.detail) {
        existing.detail = patch.detail;
        if (!patch.synthetic) {
          existing.details = [...(existing.details ?? []), patch.detail].slice(-6);
        }
      } else if (patch.state === "done" && existing.synthetic) {
        existing.detail = undefined;
      }
      existing.synthetic = patch.synthetic;
      if (patch.state === "done" && !existing.endedAt) existing.endedAt = now;
      if (patch.state === "running") existing.endedAt = undefined;
    } else {
      steps.push({
        id: patch.id,
        label: patch.label,
        state: patch.state,
        detail: patch.detail,
        details: patch.detail && !patch.synthetic ? [patch.detail] : [],
        synthetic: patch.synthetic,
        startedAt: now,
        endedAt: patch.state === "done" ? now : undefined,
      });
    }
    assistantMessage.steps = steps;
  }

  function markFirstVisibleToken(): void {
    if (assistantMessage.isThinking) {
      assistantMessage.isThinking = false;
      assistantMessage.thinkingEndAt = Date.now();
      assistantMessage.thinkingExpanded = false;
    }
  }

  function takeVisibleChunk(): string {
    const size = pendingContent.length > 800 ? 96 : pendingContent.length > 240 ? 56 : 28;
    const chunk = pendingContent.slice(0, size);
    pendingContent = pendingContent.slice(chunk.length);
    return chunk;
  }

  async function finalizeStream(): Promise<void> {
    if (streamFinalized) return;
    streamFinalized = true;
    window.clearInterval(heartbeatTimer);
    if (thinkingPreviewTimer !== null) {
      window.clearTimeout(thinkingPreviewTimer);
      thinkingPreviewTimer = null;
    }
    if (thinkingBuffer) {
      assistantMessage.thinkingPreview = thinkingBuffer.slice(-900);
      assistantMessage.thinkingFull = thinkingBuffer;
      assistantMessage.thinking = thinkingBuffer;
      assistantMessage.thinkingStats = {
        chars: thinkingBuffer.length,
        chunks: thinkingChunks,
        lastUpdatedAt: Date.now(),
      };
    }
    // 兜底：极端情况下整轮没有正式 token（例如纯 thinking 后流就结束了），
    // 也要把 isThinking 收尾，避免气泡一直转圈。
    if (assistantMessage.isThinking) {
      assistantMessage.isThinking = false;
      assistantMessage.thinkingEndAt = Date.now();
    }
    assistantMessage.isStreaming = false;
    streaming.value = false;
    await loadHistory();
  }

  function pumpContent(): void {
    if (pendingContent) {
      markFirstVisibleToken();
      assistantMessage.content += takeVisibleChunk();
    }
    if (pendingContent) {
      contentTimer = window.setTimeout(pumpContent, 45);
      return;
    }
    contentTimer = null;
    if (streamDone) {
      void finalizeStream();
    }
  }

  function scheduleContentPump(): void {
    if (contentTimer !== null) return;
    contentTimer = window.setTimeout(pumpContent, 0);
  }

  function flushThinkingPreview(): void {
    thinkingPreviewTimer = null;
    assistantMessage.thinkingPreview = thinkingBuffer.slice(-900);
    assistantMessage.thinkingStats = {
      chars: thinkingBuffer.length,
      chunks: thinkingChunks,
      lastUpdatedAt: Date.now(),
    };
  }

  function scheduleThinkingPreview(): void {
    if (thinkingPreviewTimer !== null) return;
    thinkingPreviewTimer = window.setTimeout(flushThinkingPreview, 350);
  }

  streamHandle?.close();
  streamHandle = openChatStream(currentSessionId.value, query, {
    onToken(token) {
      noteStreamEvent();
      pendingContent += token;
      scheduleContentPump();
    },
    onThinking(chunk) {
      noteStreamEvent();
      thinkingBuffer += chunk;
      thinkingChunks += 1;
      scheduleThinkingPreview();
    },
    onStatus(step, label, state) {
      noteStreamEvent();
      upsertStep({ id: step, label, state });
    },
    onProgress(step, detail) {
      noteStreamEvent();
      const existing = assistantMessage.steps?.find((item) => item.id === step);
      upsertStep({
        id: step,
        label: existing?.label ?? "正在处理",
        state: existing?.state ?? "running",
        detail,
      });
    },
    onTrace(step, label, state, detail) {
      noteStreamEvent();
      upsertStep({ id: step, label, state, detail });
    },
    onSources(sources: SourceFile[]) {
      assistantMessage.sources = sources;
    },
    onArtifact(artifact: ChatArtifact) {
      assistantMessage.artifacts = [...(assistantMessage.artifacts ?? []), artifact];
    },
    async onDone() {
      noteStreamEvent();
      streamDone = true;
      flushThinkingPreview();
      if (!pendingContent && contentTimer === null) {
        await finalizeStream();
      }
    },
    onError(message) {
      window.clearInterval(heartbeatTimer);
      if (contentTimer !== null) {
        window.clearTimeout(contentTimer);
        contentTimer = null;
      }
      if (thinkingPreviewTimer !== null) {
        window.clearTimeout(thinkingPreviewTimer);
        thinkingPreviewTimer = null;
      }
      if (pendingContent) {
        markFirstVisibleToken();
        assistantMessage.content += pendingContent;
        pendingContent = "";
      }
      if (thinkingBuffer) {
        assistantMessage.thinkingPreview = thinkingBuffer.slice(-900);
        assistantMessage.thinkingFull = thinkingBuffer;
        assistantMessage.thinking = thinkingBuffer;
      }
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

// 是否展示详细过程：关闭时仍保留简洁状态条，避免用户看到空等。
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
    <!-- 顶部全宽 Header：左侧品牌名占满左边，右侧用户菜单 -->
    <a-layout-header class="app-header">
      <!-- <div class="app-header__brand">企业智能办公助手</div> -->
       <!-- 品牌区 -->
      <div class="app-header__brand">
       
       
          企业智能办公助手 （RuiRui AI）
         

      </div>

      <!-- 个人信息：点击头像展开下拉，包含姓名/角色/部门/退出 -->
      <a-dropdown :trigger="['click']" placement="bottomRight">
        <button type="button" class="app-header__user">
          <span class="app-header__avatar">{{ userInitial }}</span>
          <span class="app-header__username">{{ sessionState.user?.name ?? "未登录" }}</span>
          <DownOutlined class="app-header__caret" />
        </button>
        <template #overlay>
          <a-menu class="app-header__menu">
            <a-menu-item-group>
              <template #title>
                <div class="app-header__profile">
                  <p class="app-header__profile-name">
                    {{ sessionState.user?.name ?? "-" }}
                  </p>
                  <p class="app-header__profile-line">
                    <span class="app-header__profile-key">角色</span>
                    <span>{{ sessionState.user?.role ?? "-" }}</span>
                  </p>
                  <p class="app-header__profile-line">
                    <span class="app-header__profile-key">部门</span>
                    <span>{{ sessionState.user?.department ?? "-" }}</span>
                  </p>
                  <p class="app-header__profile-line">
                    <span class="app-header__profile-key">能力</span>
                    <span>知识 / 薪酬 / 个人 / 商旅</span>
                  </p>
                </div>
              </template>
            </a-menu-item-group>
            <a-menu-divider />
            <a-menu-item key="logout" @click="handleLogout">
              <LogoutOutlined />
              <span>退出登录</span>
            </a-menu-item>
          </a-menu>
        </template>
      </a-dropdown>
    </a-layout-header>

    <a-layout class="workspace-body">
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
        <!-- 当前会话标题条：保留新建会话按钮 -->
        <a-card :bordered="false" class="header-card">
          <div class="header-card__top">
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
            <a-button type="primary" @click="startNewSession">
              <template #icon><PlusOutlined /></template>
              新建会话
            </a-button>
          </div>
          <!-- <a-typography-paragraph type="secondary" class="header-card__desc">
            在一个统一入口中完成知识检索、薪酬查询、个人信息查询与商旅代办。
          </a-typography-paragraph> -->
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
              <!-- <h2 class="chat-card__title">与企业智能办公助手交流</h2> -->
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
                title="开启后展示步骤详情、处理日志和推理摘录；关闭后仍保留简洁状态，避免等待感。"
              >
                <span class="composer__toggle">
                  <a-switch
                    v-model:checked="showThinking"
                    size="small"
                    checked-children="详细"
                    un-checked-children="简洁"
                  />
                  <span class="composer__toggle-label">详细过程</span>
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
  </a-layout>
</template>

<style scoped>
.workspace-layout {
  min-height: 100vh;
  background: #f8fafc;
}

/* 顶部全宽 Header */
.app-header {
  position: sticky;
  top: 0;
  z-index: 50;
  height: 64px;
  padding: 0 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #ffffff !important;
  border-bottom: 1px solid #fee2e2;
  box-shadow: 0 2px 12px -8px rgba(15, 23, 42, 0.12);
}

.app-header__brand {
  font-size: 20px;
  font-weight: 800;
  color: #1f2937;
  letter-spacing: 0.04em;
}

.app-header__user {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px 6px 6px;
  border-radius: 999px;
  background: #fff5f5;
  border: 1px solid #fee2e2;
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease;
}

.app-header__user:hover {
  background: #ffe4e6;
  border-color: #fecaca;
}

.app-header__avatar {
  width: 30px;
  height: 25px;
  border-radius: 50%;
  background: #b30000;
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 13px;
}

.app-header__username {
  font-size: 13.5px;
  font-weight: 600;
  color: #1f2937;
  height: 100%;
}

.app-header__caret {
  font-size: 10px;
  color: #94a3b8;
}

.workspace-body {
  background: transparent;
}

/* dropdown 内的资料展示（写在 :deep 也能命中 menu-item-group 的 title 区） */
.app-header__profile {
  padding: 10px 12px;
  min-width: 220px;
}

.app-header__profile-name {
  margin: 0 0 8px;
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}

.app-header__profile-line {
  margin: 4px 0;
  font-size: 12.5px;
  color: #475569;
  display: flex;
  gap: 10px;
}

.app-header__profile-key {
  display: inline-block;
  width: 32px;
  color: #94a3b8;
}

/* sider 本身 sticky 在视口顶部，自身高度 100vh，让侧边栏永远可见。
   antd 的 a-layout 是 flex row 容器，sticky 在 flex item 上完全可用。 */
.workspace-sider {
  background: transparent !important;
  position: sticky !important;
  top: 64px;
  align-self: flex-start;
  height: calc(100vh - 64px) !important;
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

.header-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.header-card__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 6px;
  font-size: 24px;
  font-weight: 800;
  color: #1f2937;
}

.header-card__desc {
  margin: 8px 0 0 !important;
  max-width: 720px;
  line-height: 1.7;
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
