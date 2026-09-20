<script setup>
import { onMounted, ref } from "vue";
import { api } from "../api";

const printer = ref({});
const camera = ref({});
const cameraTest = ref(null);
const testing = ref(false);

function stateLabel(value) {
  const labels = {
    RUNNING: "打印中",
    PAUSE: "已暂停",
    FINISH: "已完成",
    FAILED: "失败",
    IDLE: "空闲"
  };

  return labels[value] || value || "未知";
}

async function load() {
  [printer.value, camera.value] = await Promise.all([
    api("/api/printer"),
    api("/api/camera")
  ]);
}

async function testCamera() {
  testing.value = true;
  try {
    cameraTest.value = await api("/api/camera/test", {
      method: "POST"
    });
  } finally {
    testing.value = false;
  }
}

onMounted(load);
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <p class="eyebrow">设备连接</p>
        <h1>设备</h1>
        <p>检查拓竹打印机与小蚁摄像头的连接状态。</p>
      </div>
    </div>

    <div class="grid two">
      <article class="card">
        <div class="card-title">
          <span>拓竹打印机</span>
          <span>{{ stateLabel(printer.state) }}</span>
        </div>

        <dl>
          <dt>当前层数</dt>
          <dd>
            {{ printer.layer ?? "—" }}
            /
            {{ printer.total_layers ?? "—" }}
          </dd>

          <dt>打印进度</dt>
          <dd>{{ printer.progress ?? "—" }}%</dd>

          <dt>当前任务</dt>
          <dd>{{ printer.job_name || "—" }}</dd>

          <dt>任务唯一键</dt>
          <dd>{{ printer.job_key || "—" }}</dd>
        </dl>
      </article>

      <article class="card">
        <div class="card-title">
          <span>小蚁摄像头</span>
          <span>
            {{
              cameraTest
                ? (cameraTest.online ? "在线" : "离线")
                : "待检测"
            }}
          </span>
        </div>

        <dl>
          <dt>IP 地址</dt>
          <dd>{{ camera.ip || "—" }}</dd>

          <dt>用户名</dt>
          <dd>{{ camera.user || "—" }}</dd>

          <dt>配置状态</dt>
          <dd>{{ camera.configured ? "已配置" : "未配置" }}</dd>

          <template v-if="cameraTest">
            <dt>连接延迟</dt>
            <dd>{{ cameraTest.duration_ms ?? "—" }} ms</dd>
          </template>
        </dl>

        <button
          class="button"
          :disabled="testing"
          @click="testCamera"
        >
          {{ testing ? "正在检测…" : "检测摄像头" }}
        </button>
      </article>
    </div>
  </section>
</template>
