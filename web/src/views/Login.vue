<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { login } from "../auth";

const router = useRouter();
const username = ref("admin");
const password = ref("");
const error = ref("");
const loading = ref(false);

async function submit() {
  error.value = "";
  loading.value = true;

  try {
    const user = await login(username.value, password.value);

    if (user.must_change_password) {
      router.replace("/change-password");
    } else {
      router.replace("/");
    }
  } catch (e) {
    error.value = e.message || "登录失败";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-panel">
      <div class="auth-brand">
        <div class="brand-mark">B</div>
        <div>
          <strong>Bambu Timelapse</strong>
          <small>拓竹延时摄影服务</small>
        </div>
      </div>

      <div class="auth-heading">
        <p class="eyebrow">系统登录</p>
        <h1>欢迎回来</h1>
        <p>登录后管理打印任务、摄像头与延时视频。</p>
      </div>

      <form class="auth-form" @submit.prevent="submit">
        <label>
          <span>账号</span>
          <input
            v-model.trim="username"
            autocomplete="username"
            placeholder="请输入账号"
            required
          />
        </label>

        <label>
          <span>密码</span>
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="请输入密码"
            required
            autofocus
          />
        </label>

        <p v-if="error" class="form-error">{{ error }}</p>

        <button class="button auth-submit" :disabled="loading">
          {{ loading ? "正在登录…" : "登录" }}
        </button>
      </form>

      <p class="auth-hint">
        初始账号为 admin / admin，首次登录后必须修改密码。
      </p>
    </div>
  </div>
</template>
