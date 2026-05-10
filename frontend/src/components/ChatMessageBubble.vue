<script setup lang="ts">
import DOMPurify from "dompurify";
import { marked } from "marked";
import { computed, onBeforeUnmount, ref, watch } from "vue";

import type { ChatMessage } from "../types";

const props = defineProps<{
  message: ChatMessage;
}>();

const expanded = ref(false);

// 一个 250ms 心跳，让"思考中... 3.2s"的秒数能实时跳动。
// 只在该气泡的 isThinking=true 时启动；结束就销毁，避免无意义的重渲染。
const liveNow = ref(Date.now());
let liveTimer: ReturnType<typeof setInterval> | null = null;

function startTimer() {
  if (liveTimer) return;
  liveTimer = setInterval(() => {
    liveNow.value = Date.now();
  }, 250);
}
function stopTimer() {
  if (liveTimer) {
    clearInterval(liveTimer);
    liveTimer = null;
  }
}

// 心跳要在两种情况下运行：
// 1. 还在思考中（驱动"思考中 X.Xs"秒表）
// 2. 还有 running 状态的节点步骤（驱动该步骤的实时耗时显示，例如"组织答案中... 2.1s"）
const needsLiveTimer = computed(
  () =>
    Boolean(props.message.isThinking) ||
    (props.message.steps?.some((step) => step.state === "running") ?? false),
);
watch(
  needsLiveTimer,
  (needs) => {
    if (needs) {
      startTimer();
    } else {
      stopTimer();
    }
  },
  { immediate: true },
);
onBeforeUnmount(stopTimer);

// 思考耗时（秒，保留 1 位小数）。
// - 思考中：用 liveNow - thinkingStartAt
// - 已结束：用 thinkingEndAt - thinkingStartAt（凝固住）
const thinkingDurationLabel = computed(() => {
  const start = props.message.thinkingStartAt;
  if (!start) return "";
  const end = props.message.isThinking ? liveNow.value : props.message.thinkingEndAt ?? liveNow.value;
  const seconds = Math.max(0, (end - start) / 1000);
  return seconds.toFixed(1);
});

// 是否要显示豆包风格的"思考链"块：
// 1. 正在思考中（即使 thinking 文本还是空的，也显示带秒表的占位条）
// 2. 已经收到过 thinking 文本（结束后保留为可展开的"已深度思考"块）
// 3. 有 LangGraph 节点级进度需要展示（即使模型不走 reasoning，节点状态也能撑场）
const showThinkingBlock = computed(() => {
  return Boolean(
    props.message.isThinking ||
      props.message.thinking ||
      (props.message.steps && props.message.steps.length > 0),
  );
});

/** 步骤列表是否还要继续显示。
 * - 流仍在进行中：显示，让用户看进度
 * - 流已结束：仍保留，让用户能回顾经过了哪些节点（与 Claude Code/Cursor 一致） */
const stepsList = computed(() => props.message.steps ?? []);

/** 单个步骤已经耗时多久（仅 done 状态展示静态值，running 状态用心跳实时刷新）。 */
function stepDurationLabel(step: { startedAt: number; endedAt?: number }): string {
  const end = step.endedAt ?? liveNow.value;
  const ms = Math.max(0, end - step.startedAt);
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function toggleThinking() {
  // Vue 的响应式代理直接改 prop 字段是合法的（父组件传的是 reactive 对象引用）。
  props.message.thinkingExpanded = !props.message.thinkingExpanded;
}

// 强制使用同步模式，避免 marked v15+ 默认返回 Promise 时 v-html 渲染为空。
marked.use({ async: false });

// 把模型返回的 <think>...</think> 段替换成可折叠的 HTML <details> 块。
// 同时兼容流式过程中“只来了 <think> 还没等到 </think>”的中间态。
function transformThinkBlocks(raw: string): string {
  // 1. 已经闭合的：<think>xxx</think> → <details>...</details>
  let result = raw.replace(
    /<think>([\s\S]*?)<\/think>/g,
    (_, inner) =>
      `<details class="think-block" open><summary>思考过程</summary>\n\n${inner.trim()}\n\n</details>\n\n`,
  );
  // 2. 流式中尚未闭合的：<think>xxx（后面还没到）
  //    把它当成一个进行中的思考块，等闭合标签到了下一帧 computed 会重算覆盖。
  result = result.replace(
    /<think>([\s\S]*)$/,
    (_, inner) =>
      `<details class="think-block" open><summary>思考中…</summary>\n\n${inner}\n\n</details>`,
  );
  return result;
}

const htmlContent = computed(() => {
  const preprocessed = transformThinkBlocks(props.message.content);
  const rawHtml = marked.parse(preprocessed, { async: false }) as string;
  return DOMPurify.sanitize(rawHtml, {
    // 显式允许 details/summary，让 DOMPurify 不要把它们当作未知标签丢掉。
    ADD_TAGS: ["details", "summary"],
    ADD_ATTR: ["open"],
  });
});
</script>

<template>
  <div class="bubble-row" :class="`bubble-row--${message.role}`">
    <article class="bubble" :class="`bubble--${message.role}`">
      <!--
        #header 插槽：默认渲染角色标签（"我" / "智能助手"）。
        想换成头像、徽章、姓名+时间组合时，外面传一段 <template #header> 即可。
      -->
      <slot name="header" :message="message">
        <p class="bubble__role">
          {{ message.role === "user" ? "我" : "智能助手" }}
        </p>
      </slot>

      <!--
        豆包风格的"思考链"折叠块：放在内容上方。
        - 思考中：左侧旋转图标 + "思考中… X.Xs"（X 实时跳动）
        - 思考完成：齿轮图标 + "已深度思考 X.Xs"，点击展开看原文
        - 流式过程中如果 thinking 还有内容，展开后会持续追加
      -->
      <div
        v-if="message.role === 'assistant' && showThinkingBlock"
        class="thinking"
        :class="{
          'thinking--active': message.isThinking,
          'thinking--expanded': message.thinkingExpanded,
        }"
      >
        <button
          type="button"
          class="thinking__header"
          :disabled="!message.thinking"
          @click="toggleThinking"
        >
          <span class="thinking__icon" aria-hidden="true">
            <span v-if="message.isThinking" class="thinking__spinner" />
            <svg v-else viewBox="0 0 16 16" width="14" height="14">
              <path
                fill="currentColor"
                d="M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13Zm.75 3a.75.75 0 1 0-1.5 0v3.69l-2.22 2.22a.75.75 0 1 0 1.06 1.06l2.44-2.44a.75.75 0 0 0 .22-.53V4.5Z"
              />
            </svg>
          </span>
          <span class="thinking__label">
            {{ message.isThinking ? "思考中" : "已深度思考" }}
            <span class="thinking__duration">{{ thinkingDurationLabel }}s</span>
          </span>
          <span v-if="message.thinking" class="thinking__caret" aria-hidden="true">
            <svg
              viewBox="0 0 12 12"
              width="10"
              height="10"
              :style="{
                transform: message.thinkingExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
                transition: 'transform 0.2s ease',
              }"
            >
              <path fill="currentColor" d="M4 2.5 8 6 4 9.5z" />
            </svg>
          </span>
        </button>
        <!-- LangGraph 节点级进度列表：撑住"模型还没吐 token"的冷场。
             - running 步骤：左侧 spinner + 实时耗时
             - done 步骤：左侧灰色对勾 + 凝固耗时
             无论 thinkingExpanded 状态如何都展示，因为这是关键的"它现在在干什么"信息。 -->
        <ul v-if="stepsList.length" class="thinking__steps">
          <li
            v-for="step in stepsList"
            :key="step.id"
            class="thinking__step"
            :class="`thinking__step--${step.state}`"
          >
            <span class="thinking__step-icon" aria-hidden="true">
              <span v-if="step.state === 'running'" class="thinking__step-spinner" />
              <svg v-else viewBox="0 0 12 12" width="11" height="11">
                <path
                  fill="currentColor"
                  d="M10.28 3.22a.75.75 0 0 1 0 1.06l-5 5a.75.75 0 0 1-1.06 0l-2.5-2.5a.75.75 0 0 1 1.06-1.06L4.75 7.69l4.47-4.47a.75.75 0 0 1 1.06 0Z"
                />
              </svg>
            </span>
            <span class="thinking__step-label">{{ step.label }}</span>
            <span class="thinking__step-duration">{{ stepDurationLabel(step) }}</span>
          </li>
        </ul>
        <div v-if="message.thinkingExpanded && message.thinking" class="thinking__body">
          {{ message.thinking }}
        </div>
      </div>

      <!--
        #default 插槽：默认渲染 markdown 内容。
        想加自定义渲染（如代码高亮、表格组件）可以覆盖整个内容区。
      -->
      <slot :html-content="htmlContent" :message="message">
        <div v-if="message.content" class="bubble__body" v-html="htmlContent" />
      </slot>

      <!--
        打字光标：在助手气泡的"思考结束 → 流仍未 done"窗口期闪烁，
        让用户明确感知"还在出字"，避免文字稳定后误以为已结束。
        - 思考阶段：思考块自己有秒表 + 转圈，所以这里不显示
        - 流结束：done/error 后 isStreaming=false，光标消失
      -->
      <span
        v-if="
          message.role === 'assistant' &&
          message.isStreaming &&
          !message.isThinking
        "
        class="typing-cursor"
        aria-label="正在生成"
      />


      <!--
        #actions 插槽：放在内容下方、来源之上。默认空。
        典型用法：复制按钮、点赞、重新生成。
      -->
      <slot name="actions" :message="message" />

      <div v-if="message.sources?.length" class="bubble__sources">
        <button
          type="button"
          class="bubble__sources-toggle"
          @click="expanded = !expanded"
        >
          {{ expanded ? "收起来源" : "查看来源" }}
        </button>

        <div v-if="expanded" class="bubble__sources-list">
          <div
            v-for="source in message.sources"
            :key="`${source.doc_id}-${source.page_num}`"
            class="bubble__source-item"
          >
            <div class="bubble__source-meta">
              <span class="bubble__source-name">{{ source.source_file }}</span>
              <span>第{{ source.page_num }}段</span>
              <span>{{ source.department }}</span>
              <span>相关度 {{ source.score }}</span>
            </div>
            <p class="bubble__source-snippet">
              {{ source.snippet }}
            </p>
          </div>
        </div>
      </div>

      <!--
        #footer 插槽：放在气泡内底部。默认空。
        典型用法：放"已读"、"耗时 1.2s"等贴气泡的小标签。
        时间戳已经迁移到气泡外（见下方 .bubble-row__time）。
      -->
      <slot name="footer" :message="message" />
    </article>

    <!--
      时间戳：放在气泡外面，左/右对齐由 .bubble-row 决定。
      这样气泡本身只承载内容，符合现代 IM（豆包 / WeChat / Slack）的视觉规范。
    -->
    <p class="bubble-row__time">{{ message.createdAt }}</p>
  </div>
</template>

<style scoped>
.bubble-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  /* 整行最大宽度跟原来 .bubble 一致，气泡 + 时间戳一起左/右对齐 */
}

.bubble-row--user {
  align-items: flex-end;
}

.bubble-row--assistant {
  align-items: flex-start;
}

.bubble-row__time {
  margin: 0;
  padding: 0 6px;
  font-size: 11px;
  color: rgba(15, 23, 42, 0.4);
  font-variant-numeric: tabular-nums;
}

.bubble {
  max-width: 78%;
  padding: 14px 18px;
  border-radius: 22px;
  box-shadow: 0 4px 16px -8px rgba(15, 23, 42, 0.08);
  font-size: 14px;
  line-height: 1.7;
}

.bubble--user {
  background: #b30000;
  color: #fff;
}

.bubble--assistant {
  background: #fff;
  color: #1e293b;
  border: 1px solid #f1f5f9;
}

.bubble__role {
  margin: 0 0 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.22em;
  text-transform: uppercase;
}

.bubble--user .bubble__role {
  color: rgba(255, 255, 255, 0.85);
}

.bubble--assistant .bubble__role {
  color: #b30000;
}

.bubble__body {
  word-wrap: break-word;
}

.bubble__body :deep(p) {
  margin: 0 0 8px;
}

.bubble__body :deep(p:last-child) {
  margin-bottom: 0;
}

.bubble__body :deep(code) {
  background: rgba(0, 0, 0, 0.06);
  padding: 1px 6px;
  border-radius: 6px;
  font-size: 12.5px;
}

.bubble--user .bubble__body :deep(code) {
  background: rgba(255, 255, 255, 0.18);
  color: #fff;
}

.bubble__sources {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}

.bubble--user .bubble__sources {
  border-top-color: rgba(255, 255, 255, 0.2);
}

.bubble__sources-toggle {
  background: transparent;
  border: 0;
  padding: 0;
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: #b30000;
}

.bubble--user .bubble__sources-toggle {
  color: #fff;
}

.bubble__sources-list {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bubble__source-item {
  padding: 10px 12px;
  border-radius: 12px;
  background: #fff5f5;
  border: 1px solid #fee2e2;
}

.bubble__source-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 11px;
  color: #b30000;
}

.bubble__source-name {
  font-weight: 600;
}

.bubble__source-snippet {
  margin: 6px 0 0;
  font-size: 13px;
  color: #475569;
  line-height: 1.6;
}

/* === 流式期间的尾部打字光标 === */
.typing-cursor {
  display: inline-block;
  width: 8px;
  height: 16px;
  margin-left: 2px;
  vertical-align: text-bottom;
  background: currentColor;
  opacity: 0.65;
  border-radius: 1px;
  animation: typing-blink 1s steps(2, start) infinite;
}

@keyframes typing-blink {
  to {
    visibility: hidden;
  }
}

/* === 豆包风格"思考链"折叠块 === */
.thinking {
  margin: 4px 0 10px;
  border-radius: 10px;
  background: #f5f5f7;
  border: 1px solid #ececf0;
  overflow: hidden;
  font-size: 12.5px;
  color: #6b7280;
}

.thinking--active {
  background: #f7f5ff;
  border-color: #e6e0ff;
}

.thinking__header {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: transparent;
  border: 0;
  cursor: pointer;
  text-align: left;
  color: inherit;
  font: inherit;
}

.thinking__header:disabled {
  cursor: default;
}

.thinking__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  color: #8b5cf6;
}

.thinking--active .thinking__icon {
  color: #8b5cf6;
}

.thinking__spinner {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid rgba(139, 92, 246, 0.25);
  border-top-color: #8b5cf6;
  animation: thinking-spin 0.9s linear infinite;
}

@keyframes thinking-spin {
  to {
    transform: rotate(360deg);
  }
}

.thinking__label {
  flex: 1;
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  font-weight: 500;
  color: #4b5563;
}

.thinking--active .thinking__label {
  color: #6d28d9;
}

.thinking__duration {
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  color: #9ca3af;
}

.thinking--active .thinking__duration {
  color: #8b5cf6;
}

.thinking__caret {
  display: inline-flex;
  color: #9ca3af;
  flex-shrink: 0;
}

.thinking__body {
  padding: 0 12px 10px 36px;
  color: #6b7280;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
  border-top: 1px dashed rgba(0, 0, 0, 0.06);
  margin-top: 0;
  padding-top: 8px;
  font-size: 12.5px;
}

/* === LangGraph 节点级步骤列表 === */
.thinking__steps {
  margin: 0;
  padding: 4px 12px 10px 36px;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
  border-top: 1px dashed rgba(0, 0, 0, 0.06);
  padding-top: 8px;
}

.thinking__step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  line-height: 1.5;
  color: #6b7280;
  font-variant-numeric: tabular-nums;
}

.thinking__step--running {
  color: #6d28d9;
  font-weight: 500;
}

.thinking__step--done {
  color: #9ca3af;
}

.thinking__step-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.thinking__step--done .thinking__step-icon {
  color: #10b981;
}

.thinking__step-spinner {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 1.6px solid rgba(139, 92, 246, 0.25);
  border-top-color: #8b5cf6;
  animation: thinking-spin 0.9s linear infinite;
}

.thinking__step-label {
  flex: 1;
}

.thinking__step-duration {
  font-size: 11px;
  color: #b3b8c2;
}

.thinking__step--running .thinking__step-duration {
  color: #a78bfa;
}
</style>
