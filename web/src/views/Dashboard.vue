<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { api, connectEvents } from "../api";

const data = ref({ printer: {}, camera: {}, job: null, events: [] });
const loading = ref(true);
let socket;
let timer;

const progress = computed(() => Number(data.value.printer?.progress || 0));
const statusClass = computed(() =>
  data.value.printer?.state === "RUNNING" ? "ok" :
  data.value.printer?.state === "PAUSE" ? "warn" : "muted"
);

async function refresh() {
  try {
    data.value = await api("/api/status");
  } finally {
    loading.value = false;
  }
}

async function captureNow() {
  try {
    await api("/api/camera/snapshot", { method: "POST" });
  } catch (e) {
    alert(e.message);
  }
}

onMounted(async () => {
  await refresh();
  socket = connectEvents((event) => {
    data.value.events = [event, ...(data.value.events || [])].slice(0, 20);
    if (["PRINT_PROGRESS", "PRINT_STARTED", "PRINT_FINISHED", "SNAPSHOT_SUCCESS"].includes(event.type)) {
      refresh();
    }
  });
  timer = setInterval(refresh, 15000);
});

onBeforeUnmount(() => {
  socket?.close();
  clearInterval(timer);
});
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <p class="eyebrow">LIVE STATUS</p>
        <h1>Dashboard</h1>
        <p>打印状态、摄像头与自动抓拍任务概览。</p>
      </div>
      <span class="badge" :class="statusClass">{{ data.printer?.state || "IDLE" }}</span>
    </div>

    <div v-if="loading" class="card">Loading...</div>

    <template v-else>
      <div class="grid two">
        <article class="card hero-card">
          <div class="card-title">
            <span>Printer</span>
            <span class="status-text">{{ data.printer?.state || "Unknown" }}</span>
          </div>
          <h2>Bambu Lab</h2>
          <div class="metric-row">
            <div>
              <small>Progress</small>
              <strong>{{ progress }}%</strong>
            </div>
            <div>
              <small>Layer</small>
              <strong>{{ data.printer?.layer ?? "—" }} / {{ data.printer?.total_layers ?? "—" }}</strong>
            </div>
          </div>
          <div class="progress"><i :style="{ width: progress + '%' }"></i></div>
        </article>

        <article class="card">
          <div class="card-title">
            <span>Yi Camera</span>
            <span class="status-text">Configured</span>
          </div>
          <h2>{{ data.camera?.ip || "Not configured" }}</h2>
          <p class="subtle">HTTP Snapshot / High Resolution</p>
          <button class="button" @click="captureNow">Capture now</button>
        </article>
      </div>

      <article class="card current-job">
        <div class="card-title">
          <span>Current Print</span>
          <span>#{{ data.job?.id || "—" }}</span>
        </div>
        <div v-if="data.job" class="job-grid">
          <div><small>Name</small><strong>{{ data.job.name }}</strong></div>
          <div><small>Status</small><strong>{{ data.job.status }}</strong></div>
          <div><small>Frames</small><strong>{{ data.job.frame_count }}</strong></div>
          <div><small>Failed</small><strong>{{ data.job.failed_frames }}</strong></div>
        </div>
        <p v-else class="empty">当前没有活动打印任务。</p>
      </article>

      <article class="card">
        <div class="card-title"><span>Events</span><span>Realtime</span></div>
        <div class="events">
          <div v-for="(event, index) in data.events" :key="index" class="event">
            <span class="event-type">{{ event.type }}</span>
            <span>{{ event.message }}</span>
            <time>{{ new Date(event.time).toLocaleTimeString() }}</time>
          </div>
        </div>
      </article>
    </template>
  </section>
</template>
