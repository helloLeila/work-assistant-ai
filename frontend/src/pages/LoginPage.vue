<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { UserOutlined, LockOutlined } from "@ant-design/icons-vue";

import { requestJson } from "../lib/api";
import { setSession } from "../stores/session";
import type { UserProfile } from "../types";

const router = useRouter();
const loading = ref(false);
const errorMessage = ref("");

const formState = reactive({
  username: "li.wei",
  password: "RuiRui123!",
});

async function handleLogin(): Promise<void> {
  loading.value = true;
  errorMessage.value = "";
  try {
    const payload = await requestJson<{
      access_token: string;
      refresh_token: string;
      user: UserProfile;
    }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: formState.username,
        password: formState.password,
      }),
    });

    setSession(
      {
        accessToken: payload.access_token,
        refreshToken: payload.refresh_token,
      },
      payload.user,
    );
    await router.push("/workspace");
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "登录失败";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <main class="login-shell">
    <!-- 左侧品牌区 -->
    <section class="login-brand">
      <div class="login-brand__top">
        <p class="login-brand__eyebrow">AI OFFICE ASSISTANT</p>
        <h1 class="login-brand__title">企业级智能办公助手</h1>
        <p class="login-brand__desc">
          将知识检索、权限控制、敏感信息脱敏和商旅代办整合到同一条智能对话链路中，
          面向企业员工提供统一的办公入口。
        </p>
      </div>

      <div class="login-brand__features">
        <div class="feature-card">
          <p class="feature-card__eyebrow">Knowledge</p>
          <p class="feature-card__title">企业知识检索</p>
        </div>
        <div class="feature-card">
          <p class="feature-card__eyebrow">Secure</p>
          <p class="feature-card__title">权限与脱敏控制</p>
        </div>
        <div class="feature-card">
          <p class="feature-card__eyebrow">Travel</p>
          <p class="feature-card__title">商旅结构化代办</p>
        </div>
      </div>
    </section>

    <!-- 右侧表单区 -->
    <section class="login-form-wrap">
      <a-card :bordered="false" class="login-form-card">
        <a-typography-text type="secondary" class="login-form-card__eyebrow">
          Welcome Back
        </a-typography-text>
        <h2 class="login-form-card__title">登录企业智能办公助手</h2>
        <a-typography-paragraph type="secondary">
          输入账号和密码后即可进入统一工作台。
        </a-typography-paragraph>

        <a-form
          layout="vertical"
          :model="formState"
          @finish="handleLogin"
        >
          <a-form-item
            label="账号"
            name="username"
            :rules="[{ required: true, message: '请输入账号' }]"
          >
            <a-input
              v-model:value="formState.username"
              size="large"
              placeholder="请输入账号"
            >
              <template #prefix><UserOutlined /></template>
            </a-input>
          </a-form-item>

          <a-form-item
            label="密码"
            name="password"
            :rules="[{ required: true, message: '请输入密码' }]"
          >
            <a-input-password
              v-model:value="formState.password"
              size="large"
              placeholder="请输入密码"
            >
              <template #prefix><LockOutlined /></template>
            </a-input-password>
          </a-form-item>

          <a-alert
            v-if="errorMessage"
            type="error"
            :message="errorMessage"
            show-icon
            class="login-alert"
          />

          <a-button
            type="primary"
            html-type="submit"
            block
            size="large"
            :loading="loading"
          >
            {{ loading ? "登录中..." : "进入工作台" }}
          </a-button>
        </a-form>
      </a-card>
    </section>
  </main>
</template>

<style scoped>
.login-shell {
  display: grid;
  min-height: 100vh;
  grid-template-columns: 1fr;
}

@media (min-width: 1024px) {
  .login-shell {
    grid-template-columns: 1.2fr 0.8fr;
  }
}

/* 左侧品牌 */
.login-brand {
  display: none;
  position: relative;
  overflow: hidden;
  padding: 56px;
  color: #fff;
  background: linear-gradient(165deg, #4c0519 0%, #881337 45%, #b30000 100%);
}

@media (min-width: 1024px) {
  .login-brand {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }
}

.login-brand__eyebrow {
  font-size: 12px;
  letter-spacing: 0.4em;
  text-transform: uppercase;
  color: #fecdd3;
  margin: 0;
}

.login-brand__title {
  margin: 20px 0 24px;
  font-size: 44px;
  font-weight: 900;
  line-height: 1.15;
  max-width: 540px;
}

.login-brand__desc {
  font-size: 16px;
  line-height: 1.8;
  color: #ffe4e6;
  max-width: 640px;
  margin: 0;
}

.login-brand__features {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  max-width: 720px;
}

.feature-card {
  padding: 20px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.16);
}

.feature-card__eyebrow {
  font-size: 11px;
  letter-spacing: 0.28em;
  text-transform: uppercase;
  color: #fecdd3;
  margin: 0;
}

.feature-card__title {
  margin: 12px 0 0;
  font-size: 16px;
  font-weight: 600;
}

/* 右侧表单 */
.login-form-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
  background: #fff5f7;
}

.login-form-card {
  width: 100%;
  max-width: 520px;
  border-radius: 28px !important;
  box-shadow: 0 30px 60px -20px rgba(190, 18, 60, 0.18) !important;
}

.login-form-card :deep(.ant-card-body) {
  padding: 36px 36px 32px;
}

.login-form-card__eyebrow {
  font-size: 12px;
  letter-spacing: 0.32em;
  text-transform: uppercase;
  color: #b30000 !important;
}

.login-form-card__title {
  margin: 16px 0 12px;
  font-size: 26px;
  font-weight: 800;
  color: #0f172a;
}

.login-alert {
  margin-bottom: 16px;
}
</style>
