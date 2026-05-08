import { sessionState } from "../stores/session";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

export function getApiBaseUrl(): string {
  return API_BASE;
}

function buildHeaders(extraHeaders?: HeadersInit): HeadersInit {
  // 除了 SSE 的 EventSource 例外场景，普通请求统一走 Bearer Token 头。
  const headers: HeadersInit = {
    ...extraHeaders,
  };

  if (sessionState.accessToken) {
    headers.Authorization = `Bearer ${sessionState.accessToken}`;
  }

  return headers;
}

export async function requestJson<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  // 所有 JSON 请求都经过这一个入口，方便后面统一接入刷新令牌、
  // 错误码翻译或埋点统计。
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: buildHeaders({
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "请求失败");
  }

  return (await response.json()) as T;
}

export async function requestFormData<T>(
  path: string,
  body: FormData,
): Promise<T> {
  // 上传文件时不要手动设置 Content-Type，
  // 让浏览器自动补上 multipart boundary。
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: buildHeaders(),
    body,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "上传失败");
  }

  return (await response.json()) as T;
}
