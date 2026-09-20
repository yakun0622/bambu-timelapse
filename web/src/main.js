import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import Dashboard from "./views/Dashboard.vue";
import Jobs from "./views/Jobs.vue";
import Devices from "./views/Devices.vue";
import Settings from "./views/Settings.vue";
import "./style.css";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: Dashboard },
    { path: "/jobs", component: Jobs },
    { path: "/devices", component: Devices },
    { path: "/settings", component: Settings }
  ]
});

createApp(App).use(router).mount("#app");
