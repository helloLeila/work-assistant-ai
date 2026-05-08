<script setup lang="ts">
import { computed, h, onMounted, ref } from "vue";
import { message as antMessage, Modal } from "ant-design-vue";
import {
  InboxOutlined,
  DeleteOutlined,
  ExclamationCircleOutlined,
} from "@ant-design/icons-vue";
import type { UploadProps } from "ant-design-vue";

import AppSidebar from "../components/AppSidebar.vue";
import { requestFormData, requestJson } from "../lib/api";
import { sessionState } from "../stores/session";
import type { HistorySession, KnowledgeDocument } from "../types";

const documents = ref<KnowledgeDocument[]>([]);
const historySessions = ref<HistorySession[]>([]);
const uploadDepartment = ref("HR");
const loading = ref(false);

const canManage = computed(
  () => sessionState.user?.role === "hr_admin" || sessionState.user?.role === "knowledge_admin",
);

// 表格列定义：放在 setup 顶部，便于复用与维护。
const tableColumns = [
  { title: "文件名", dataIndex: "filename", key: "filename", ellipsis: true },
  { title: "部门", dataIndex: "department", key: "department", width: 100 },
  { title: "类型", dataIndex: "doc_type", key: "doc_type", width: 100 },
  { title: "块数", dataIndex: "chunk_count", key: "chunk_count", width: 80 },
  { title: "上传时间", dataIndex: "upload_time", key: "upload_time", width: 180 },
  { title: "操作", key: "action", width: 120, fixed: "right" as const },
];

const departmentOptions = [
  { label: "HR", value: "HR" },
  { label: "Finance", value: "Finance" },
  { label: "IT", value: "IT" },
  { label: "Legal", value: "Legal" },
];

async function loadKnowledge(): Promise<void> {
  const payload = await requestJson<{ items: KnowledgeDocument[] }>("/knowledge/list");
  documents.value = payload.items;
}

async function loadHistory(): Promise<void> {
  const payload = await requestJson<{ items: HistorySession[]; total: number }>(
    "/chat/history?page=1&page_size=20",
  );
  historySessions.value = payload.items;
}

// a-upload 自定义请求：用我们自己的 fetch 走鉴权，不走 antd 默认的 XHR。
const customUpload: UploadProps["customRequest"] = async (options) => {
  const file = options.file as File;
  loading.value = true;
  try {
    const formData = new FormData();
    formData.append("department", uploadDepartment.value);
    formData.append("file", file);
    await requestFormData("/knowledge/upload", formData);
    options.onSuccess?.({}, new XMLHttpRequest());
    antMessage.success(`${file.name} 上传成功`);
    await loadKnowledge();
  } catch (error) {
    options.onError?.(error as Error);
    antMessage.error(error instanceof Error ? error.message : "上传失败");
  } finally {
    loading.value = false;
  }
};

function confirmDelete(doc: KnowledgeDocument): void {
  Modal.confirm({
    title: `确认删除「${doc.filename}」？`,
    icon: h(ExclamationCircleOutlined),
    content: "删除后该文档及其检索索引会一起被清理。",
    okText: "删除",
    okType: "danger",
    cancelText: "取消",
    centered: true,
    onOk: async () => {
      await requestJson(`/knowledge/${doc.doc_id}`, { method: "DELETE" });
      antMessage.success("已删除");
      await loadKnowledge();
    },
  });
}

function noop(): void {
  // 当前页面只展示历史，不切换会话。
}

onMounted(async () => {
  await Promise.all([loadKnowledge(), loadHistory()]);
});
</script>

<template>
  <a-layout class="kb-layout">
    <a-layout-sider :width="300" class="kb-sider">
      <AppSidebar
        :sessions="historySessions"
        @new-session="noop"
        @select-session="noop"
        @delete-session="noop"
        @rename-session="noop"
      />
    </a-layout-sider>

    <a-layout-content class="kb-main">
      <div class="kb-stack">
        <!-- 顶部介绍 -->
        <a-card :bordered="false" class="kb-header">
          <a-typography-text type="secondary" class="kb-eyebrow">
            Knowledge Base
          </a-typography-text>
          <h1 class="kb-title">知识库管理</h1>
          <a-typography-paragraph type="secondary" class="kb-desc">
            上传企业制度、FAQ 和操作规范，系统会完成文档切分、索引构建和检索准备。
          </a-typography-paragraph>
        </a-card>

        <a-alert
          v-if="!canManage"
          type="warning"
          message="当前账号没有知识库管理权限"
          description="请联系管理员或切换具备权限的账号。"
          show-icon
        />

        <div v-else class="kb-grid">
          <!-- 左侧：上传区 -->
          <div class="kb-upload-col">
            <a-card title="归属部门" :bordered="false">
              <a-select
                v-model:value="uploadDepartment"
                size="large"
                style="width: 100%"
                :options="departmentOptions"
              />
            </a-card>

            <a-card title="上传文档" :bordered="false">
              <a-upload-dragger
                name="file"
                :multiple="false"
                :show-upload-list="false"
                :custom-request="customUpload"
                :disabled="loading"
              >
                <p class="ant-upload-drag-icon">
                  <InboxOutlined />
                </p>
                <p class="ant-upload-text">点击或拖拽文件到此处上传</p>
                <p class="ant-upload-hint">
                  支持 PDF / Word / Markdown / TXT；上传后会自动切分入库。
                </p>
              </a-upload-dragger>
            </a-card>
          </div>

          <!-- 右侧：文档列表 -->
          <a-card
            :bordered="false"
            title="已入库文档"
            class="kb-table-card"
          >
            <a-table
              :columns="tableColumns"
              :data-source="documents"
              :pagination="{ pageSize: 8, hideOnSinglePage: true }"
              :scroll="{ x: 720 }"
              row-key="doc_id"
              size="middle"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'upload_time'">
                  {{ record.upload_time.replace('T', ' ').slice(0, 19) }}
                </template>
                <template v-if="column.key === 'action'">
                  <a-button
                    type="link"
                    danger
                    size="small"
                    @click="confirmDelete(record)"
                  >
                    <template #icon><DeleteOutlined /></template>
                    删除
                  </a-button>
                </template>
              </template>
            </a-table>
          </a-card>
        </div>
      </div>
    </a-layout-content>
  </a-layout>
</template>

<style scoped>
.kb-layout {
  min-height: 100vh;
  background: #f8fafc;
}

.kb-sider {
  background: transparent !important;
  position: sticky !important;
  top: 0;
  align-self: flex-start;
  height: 100vh !important;
}

.kb-sider :deep(.ant-layout-sider-children) {
  display: flex;
  height: 100%;
}

.kb-main {
  padding: 24px 32px;
}

.kb-stack {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.kb-header :deep(.ant-card-body) {
  padding: 24px 28px;
}

.kb-eyebrow {
  font-size: 11px;
  letter-spacing: 0.32em;
  text-transform: uppercase;
  color: #b30000 !important;
}

.kb-title {
  margin: 14px 0 6px;
  font-size: 28px;
  font-weight: 800;
  color: #0f172a;
}

.kb-desc {
  margin: 0 !important;
  max-width: 720px;
  line-height: 1.7;
}

.kb-grid {
  display: grid;
  gap: 20px;
}

@media (min-width: 1280px) {
  .kb-grid {
    grid-template-columns: 360px minmax(0, 1fr);
  }
}

.kb-upload-col {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.kb-table-card :deep(.ant-card-body) {
  padding: 16px 20px 20px;
}
</style>
