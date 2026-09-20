<script setup>
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";

import { authState, logout } from "./auth";

const route = useRoute();
const router = useRouter();

const authPage = computed(() =>
  route.path === "/login" ||
  route.path === "/change-password"
);

async function doLogout() {
  await logout();
  router.replace("/login");
}
</script>

<template>
  <RouterView v-if="authPage" />

  <div v-else class="shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">B</div>
        <div>
          <strong>Bambu Timelapse</strong>
          <small>拓竹延时摄影服务</small>
        </div>
      </div>

      <nav>
        <RouterLink to="/">控制台</RouterLink>
        <RouterLink to="/jobs">打印任务</RouterLink>
        <RouterLink to="/devices">设备</RouterLink>
        <RouterLink to="/settings">设置</RouterLink>
      </nav>

      <div class="sidebar-account">
        <div>
          <small>当前账号</small>
          <strong>{{ authState.user?.username }}</strong>
        </div>
        <button class="text-button" @click="doLogout">退出登录</button>
      </div>

      <div class="sidebar-footer">
        <span class="dot"></span>
        v0.3.0
      </div>
    </aside>

    <main class="content">
      <RouterView />
    </main>
  </div>
</template>
