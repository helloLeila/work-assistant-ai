import { createRouter, createWebHistory } from "vue-router";

import KnowledgeBasePage from "../pages/KnowledgeBasePage.vue";
import LoginPage from "../pages/LoginPage.vue";
import WorkspacePage from "../pages/WorkspacePage.vue";
import { isAuthenticated } from "../stores/session";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "login",
      component: LoginPage,
    },
    {
      path: "/workspace",
      name: "workspace",
      component: WorkspacePage,
    },
    {
      path: "/knowledge",
      name: "knowledge",
      component: KnowledgeBasePage,
    },
  ],
});

router.beforeEach((to) => {
  if (to.name === "login") {
    return true;
  }

  if (!isAuthenticated.value) {
    return { name: "login" };
  }

  return true;
});

export default router;
