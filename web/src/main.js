import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";

import App from "./App.vue";
import Dashboard from "./views/Dashboard.vue";
import Jobs from "./views/Jobs.vue";
import Devices from "./views/Devices.vue";
import Settings from "./views/Settings.vue";
import Login from "./views/Login.vue";
import ChangePassword from "./views/ChangePassword.vue";

import { authState, loadCurrentUser } from "./auth";
import "./style.css";


const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: Login, meta: { public: true } },
    { path: "/change-password", component: ChangePassword },
    { path: "/", component: Dashboard },
    { path: "/jobs", component: Jobs },
    { path: "/devices", component: Devices },
    { path: "/settings", component: Settings }
  ]
});


router.beforeEach(async (to) => {
  await loadCurrentUser();

  const user = authState.user;

  if (!user) {
    if (to.path === "/login") {
      return true;
    }
    return "/login";
  }

  if (user.must_change_password) {
    if (to.path === "/change-password") {
      return true;
    }
    return "/change-password";
  }

  if (to.path === "/login" || to.path === "/change-password") {
    return "/";
  }

  return true;
});


createApp(App)
  .use(router)
  .mount("#app");
