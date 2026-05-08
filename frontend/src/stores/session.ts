import { computed, reactive } from "vue";

import type { SessionTokens, UserProfile } from "../types";

const STORAGE_KEY = "tongtong_session";

type SessionState = {
  accessToken: string;
  refreshToken: string;
  user: UserProfile | null;
};

const initialState: SessionState = {
  accessToken: "",
  refreshToken: "",
  user: null,
};

function loadState(): SessionState {
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return initialState;
  }

  try {
    return JSON.parse(raw) as SessionState;
  } catch {
    return initialState;
  }
}

export const sessionState = reactive<SessionState>(loadState());

function persistState(): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(sessionState));
}

export function setSession(tokens: SessionTokens, user: UserProfile): void {
  sessionState.accessToken = tokens.accessToken;
  sessionState.refreshToken = tokens.refreshToken;
  sessionState.user = user;
  persistState();
}

export function clearSession(): void {
  sessionState.accessToken = "";
  sessionState.refreshToken = "";
  sessionState.user = null;
  window.localStorage.removeItem(STORAGE_KEY);
}

export const isAuthenticated = computed(() => Boolean(sessionState.accessToken));
