export interface QuickAction {
  key: string;
  title: string;
  description: string;
  prompt: string;
}

export interface SourceFile {
  doc_id: string;
  source_file: string;
  page_num: number;
  department: string;
  score: number;
  snippet: string;
}

/** LangGraph 节点级进度。后端每进入/离开一个节点都 push 一次，
 * 前端把它们累计成可视化的"步骤列表"——比如：
 *   ⟳ 检索知识库...
 *   ✓ 已筛选相关内容
 *   ⟳ 组织答案中...
 * 用来填补"模型还没吐 token"那段冷场时间。 */
export interface ChatStep {
  /** 稳定的机器 id（intent / retrieve / grade / generate ...），用于 upsert。 */
  id: string;
  /** 给用户看的中文描述，可以随节点动态变化。 */
  label: string;
  /** running = 进行中（spinner），done = 已完成（对勾）。 */
  state: "running" | "done";
  /** 当前步骤的即时说明，适合简洁模式展示。 */
  detail?: string;
  /** 可展开的过程日志，适合详细模式展示。 */
  details?: string[];
  /** 本地 heartbeat 生成的临时说明，区别于后端真实事件。 */
  synthetic?: boolean;
  /** 进入该步骤的时间戳（ms）。可以拿来显示"耗时 1.2s"。 */
  startedAt: number;
  /** 离开该步骤的时间戳（ms）。仅 state=done 时有值。 */
  endedAt?: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** 流式期间低频转换后的 Markdown HTML，避免每次 token 都重排整段正文。 */
  renderedContent?: string;
  createdAt: string;
  sources?: SourceFile[];
  /** 累积的"思考过程"原文（豆包风格折叠块的内容来源）。 */
  thinking?: string;
  /** 流式期间展示的轻量 thinking 摘录，只保留尾部窗口，避免长文本持续重绘。 */
  thinkingPreview?: string;
  /** 完整 thinking 原文。流结束后落到响应式对象，按需展开查看。 */
  thinkingFull?: string;
  /** thinking 流的轻量统计信息，用于过程面板展示接收进度。 */
  thinkingStats?: {
    chars: number;
    chunks: number;
    lastUpdatedAt: number;
  };
  /** 该助手消息开始流式响应时的时间戳（ms）。 */
  thinkingStartAt?: number;
  /** 第一段正式回答开始流出时的时间戳（ms）。用来算"已深度思考 x 秒"。 */
  thinkingEndAt?: number;
  /** 当前是否处于思考阶段（用于驱动 UI 的转圈/秒表）。 */
  isThinking?: boolean;
  /** 折叠块默认收起，点击展开。 */
  thinkingExpanded?: boolean;
  /** 整个 SSE 流是否还在进行中。done/error 后置 false，用来驱动尾部打字光标。 */
  isStreaming?: boolean;
  /** 后端 LangGraph 节点的实时进度列表，按发生顺序保存。 */
  steps?: ChatStep[];
}

export interface KnowledgeDocument {
  doc_id: string;
  filename: string;
  department: string;
  doc_type: string;
  upload_time: string;
  chunk_count: number;
}

export interface UserProfile {
  user_id: string;
  username: string;
  name: string;
  role: string;
  department: string;
  manager_id?: string | null;
}

export interface SessionTokens {
  accessToken: string;
  refreshToken: string;
}

export interface HistoryTurn {
  role: "user" | "assistant";
  content: string;
  created_at: string;
  sources: SourceFile[];
}

export interface HistorySession {
  session_id: string;
  title: string;
  updated_at: string;
  turns: HistoryTurn[];
}
