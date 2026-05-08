<script setup lang="ts">
import { theme } from "ant-design-vue";
import zhCN from "ant-design-vue/es/locale/zh_CN";

// 全局 antd 主题：玫瑰红主调色 + 跟品牌一致的圆角；中文 locale 让弹窗、表格等用中文。
const antdTheme = {
  algorithm: theme.defaultAlgorithm,
  token: {
    colorPrimary: "#b30000",
    colorInfo: "#b30000",
    colorLink: "#b30000",
    borderRadius: 12,
    fontFamily:
      'Inter, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
  },
};
</script>

<template>
  <a-config-provider :theme="antdTheme" :locale="zhCN">
    <div class="app-shell">
      <RouterView />
    </div>
  </a-config-provider>
</template>
