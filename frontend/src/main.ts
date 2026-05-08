import { createApp } from "vue";
import Antd from "ant-design-vue";
import "ant-design-vue/dist/reset.css";

import App from "./App.vue";
import router from "./router";
import "./style.css";

// 统一从这里挂载应用，方便后续补全全局状态和主题逻辑。
// Antd 全量注册：开发期省事，生产打包后 Vite Tree-shaking 会按需保留实际用到的组件。
createApp(App).use(router).use(Antd).mount("#app");
