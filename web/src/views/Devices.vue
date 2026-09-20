<script setup>
import { onMounted, ref } from "vue";
import { api } from "../api";

const printer = ref({});
const camera = ref({});
const cameraTest = ref(null);

async function load() {
  [printer.value, camera.value] = await Promise.all([
    api("/api/printer"),
    api("/api/camera")
  ]);
}

async function testCamera() {
  cameraTest.value = await api("/api/camera/test", { method: "POST" });
}

onMounted(load);
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <p class="eyebrow">INTEGRATIONS</p>
        <h1>Devices</h1>
        <p>检查打印机与摄像头连接状态。</p>
      </div>
    </div>

    <div class="grid two">
      <article class="card">
        <div class="card-title"><span>Bambu Printer</span><span>{{ printer.state || "Unknown" }}</span></div>
        <dl>
          <dt>Layer</dt><dd>{{ printer.layer ?? "—" }} / {{ printer.total_layers ?? "—" }}</dd>
          <dt>Progress</dt><dd>{{ printer.progress ?? "—" }}%</dd>
          <dt>Current Job</dt><dd>{{ printer.job_name || "—" }}</dd>
        </dl>
      </article>

      <article class="card">
        <div class="card-title"><span>Yi Camera</span><span>{{ cameraTest?.online ? "Online" : "Ready" }}</span></div>
        <dl>
          <dt>IP</dt><dd>{{ camera.ip }}</dd>
          <dt>User</dt><dd>{{ camera.user }}</dd>
          <dt>Configured</dt><dd>{{ camera.configured ? "Yes" : "No" }}</dd>
          <dt v-if="cameraTest">Response</dt><dd v-if="cameraTest">{{ cameraTest.duration_ms ?? "—" }} ms</dd>
        </dl>
        <button class="button" @click="testCamera">Test camera</button>
      </article>
    </div>
  </section>
</template>
