<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { changePassword } from "../auth";

const router = useRouter();
const currentPassword = ref("");
const newPassword = ref("");
const confirmPassword = ref("");
const error = ref("");
const loading = ref(false);

async function submit() {
  error.value = "";

  if (newPassword.value.length < 8) {
    error.value = "新密码至少需要 8 个字符";
    return;
  }

  if (newPassword.value !== confirmPassword.value) {
    error.value = "两次输入的新密码不一致";
    return;
  }

  loading.value = true;

  try {
    await changePassword(currentPassword.value, newPassword.value);
    router.replace("/");
  } catch (e) {
    error.value = e.message || "修改密码失败";
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
          <small>安全设置</small>
        </div>
      </div>

      <div class="auth-heading">
        <p class="eyebrow">首次登录</p>
        <h1>请修改默认密码</h1>
        <p>为了保护 Bambu Token、摄像头和打印任务数据，请先设置新的管理密码。</p>
      </div>

      <form class="auth-form" @submit.prevent="submit">
        <label>
          <span>当前密码</span>
          <input
            v-model="currentPassword"
            type="password"
            autocomplete="current-password"
            placeholder="请输入当前密码"
            required
            autofocus
          />
        </label>

        <label>
          <span>新密码</span>
          <input
            v-model="newPassword"
            type="password"
            autocomplete="new-password"
            placeholder="至少 8 个字符"
            required
          />
        </label>

        <label>
          <span>确认新密码</span>
          <input
            v-model="confirmPassword"
            type="password"
            autocomplete="new-password"
            placeholder="再次输入新密码"
            required
          />
        </label>

        <p v-if="error" class="form-error">{{ error }}</p>

        <button class="button auth-submit" :disabled="loading">
          {{ loading ? "正在保存…" : "修改密码并进入系统" }}
        </button>
      </form>
    </div>
  </div>
</template>
