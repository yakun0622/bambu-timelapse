<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { authState, logout } from "./auth";
import { themeState, toggleTheme, useSystemTheme } from "./theme";

const route = useRoute();
const router = useRouter();
const accountOpen = ref(false);

const authPage = computed(() =>
  route.path === "/login" ||
  route.path === "/change-password"
);

const pageTitle = computed(() => {
  const titles = {
    "/": "控制台",
    "/jobs": "打印任务",
    "/devices": "设备",
    "/settings": "设置"
  };

  return titles[route.path] || "Bambu Timelapse";
});

const userInitial = computed(() =>
  (authState.user?.username || "A")
    .charAt(0)
    .toUpperCase()
);

async function doLogout() {
  accountOpen.value = false;
  await logout();
  router.replace("/login");
}

function toggleAccount() {
  accountOpen.value = !accountOpen.value;
}

function closeAccount(event) {
  if (!event.target.closest(".topbar-account")) {
    accountOpen.value = false;
  }
}

onMounted(() => {
  document.addEventListener("click", closeAccount);
});

onBeforeUnmount(() => {
  document.removeEventListener("click", closeAccount);
});
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

      <div class="sidebar-footer">
        <span class="dot"></span>
        v0.3.0
      </div>
    </aside>

    <div class="workspace">
      <header class="topbar">
        <div class="topbar-title">
          <span>管理后台</span>
          <strong>{{ pageTitle }}</strong>
        </div>

        <div class="topbar-actions">
          <button
            class="theme-toggle"
            type="button"
            :title="
              themeState.preference === 'system'
                ? '当前跟随系统主题，点击切换主题'
                : '点击切换主题，双击恢复跟随系统'
            "
            @click="toggleTheme"
            @dblclick="useSystemTheme"
          >
            <span class="theme-icon" aria-hidden="true">
              {{ themeState.resolved === "dark" ? "☾" : "☀" }}
            </span>
            <span class="theme-label">
              {{ themeState.resolved === "dark" ? "夜间" : "白天" }}
            </span>
            <span
              v-if="themeState.preference === 'system'"
              class="theme-system-mark"
            >
              系统
            </span>
          </button>

          <div class="topbar-account">
            <button
              class="account-trigger"
              type="button"
              @click.stop="toggleAccount"
            >
              <span class="account-avatar">
                {{ userInitial }}
              </span>

              <span class="account-copy">
                <strong>{{ authState.user?.username }}</strong>
                <small>管理员</small>
              </span>

              <span
                class="account-chevron"
                :class="{ open: accountOpen }"
              >
                ▾
              </span>
            </button>

            <Transition name="account-menu">
              <div
                v-if="accountOpen"
                class="account-menu"
              >
                <div class="account-menu-head">
                  <span class="account-avatar large">
                    {{ userInitial }}
                  </span>

                  <div>
                    <strong>{{ authState.user?.username }}</strong>
                    <small>系统管理员</small>
                  </div>
                </div>

                <div class="account-menu-separator"></div>

                <RouterLink
                  to="/settings"
                  class="account-menu-item"
                  @click="accountOpen = false"
                >
                  账号与系统设置
                </RouterLink>

                <button
                  class="account-menu-item danger"
                  type="button"
                  @click="doLogout"
                >
                  退出登录
                </button>
              </div>
            </Transition>
          </div>
        </div>
      </header>

      <main class="content">
        <RouterView />
      </main>
    </div>
  </div>
</template>
