import { getApiBaseUrl } from "../lib/api";
import { sessionState } from "../stores/session";
import type { SourceFile } from "../types";

type StreamHandlers = {
  onToken: (token: string) => void;
  onThinking?: (chunk: string) => void;
  /** 后端 LangGraph 节点级进度。step 是稳定 id（intent/retrieve/grade/...），
   * label 是给用户看的中文，state 取 running | done。
   * 在'模型还没吐 token'的几秒里，前端用这个事件驱动"步骤列表"UI。 */
  onStatus?: (step: string, label: string, state: "running" | "done") => void;
  onProgress?: (step: string, detail: string) => void;
  onTrace?: (
    step: string,
    label: string,
    state: "running" | "done",
    detail: string,
  ) => void;
  onSources: (sources: SourceFile[]) => void;
  onDone: () => void;
  onError: (message: string) => void;
};

export function openChatStream(
  sessionId: string,
  query: string,
  handlers: StreamHandlers,
): EventSource {
  // 浏览器原生 EventSource 不能自定义 Authorization Header，
  // 所以这里把 access_token 放到查询参数里，由后端专门兼容处理。
  const params = new URLSearchParams({
    session_id: sessionId,
    query,
    access_token: sessionState.accessToken,
  });

  const eventSource = new EventSource(
    `${getApiBaseUrl()}/chat/stream?${params.toString()}`,
  );

  eventSource.onmessage = (event) => {
    // 后端统一按 { type, ...payload } 的结构推送事件，
    // 前端根据事件类型把 token、引用来源和结束信号拆开处理。
    const payload = JSON.parse(event.data) as {
      type: string;
      content?: string;
      files?: SourceFile[];
      message?: string;
      step?: string;
      label?: string;
      state?: "running" | "done";
      detail?: string;
    };

    if (payload.type === "token") {
      handlers.onToken(payload.content ?? "");
      return;
    }

    if (payload.type === "thinking") {
      handlers.onThinking?.(payload.content ?? "");
      return;
    }

    if (payload.type === "status") {
      // step/label/state 三件套来自后端 SSEStreamer.push_status。
      // 缺字段直接忽略，让前端对协议升级保持兼容。
      if (payload.step && payload.label && payload.state) {
        handlers.onStatus?.(payload.step, payload.label, payload.state);
      }
      return;
    }

    if (payload.type === "progress") {
      if (payload.step && payload.detail) {
        handlers.onProgress?.(payload.step, payload.detail);
      }
      return;
    }

    if (payload.type === "trace") {
      if (payload.step && payload.label && payload.state) {
        handlers.onTrace?.(
          payload.step,
          payload.label,
          payload.state,
          payload.detail ?? "",
        );
      }
      return;
    }

    if (payload.type === "source") {
      handlers.onSources(payload.files ?? []);
      return;
    }

    if (payload.type === "done") {
      handlers.onDone();
      eventSource.close();
      return;
    }

    if (payload.type === "error") {
      handlers.onError(payload.message ?? "流式请求失败");
      eventSource.close();
    }
  };

  eventSource.onerror = () => {
    handlers.onError("连接中断，请稍后重试。");
    eventSource.close();
  };

  return eventSource;
}
