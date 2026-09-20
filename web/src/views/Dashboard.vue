<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { api, connectEvents } from "../api";

const data = ref({ printer: {}, camera: {}, job: null, events: [] });
const timeline = ref([]);
const liveEvent = ref(null);
const loading = ref(true);

let socket;
let timer;

const progress = computed(() => Number(data.value.printer?.progress || 0));

const statusClass = computed(() =>
  data.value.printer?.state === "RUNNING" ? "ok" :
  data.value.printer?.state === "PAUSE" ? "warn" : "muted"
);

const isRunning = computed(() => data.value.printer?.state === "RUNNING");

function eventKey(event) {
  if (event.id !== undefined && event.id !== null) {
    return `id:${event.id}`;
  }

  return [
    event.type,
    event.message,
    event.time
  ].join("|");
}

function sortEvents(events) {
  return [...events].sort(
    (a, b) => new Date(b.time) - new Date(a.time)
  );
}

function hydrateEvents(events = []) {
  const progressEvents = events.filter(event => event.type === "PRINT_PROGRESS");

  if (progressEvents.length) {
    liveEvent.value = sortEvents(progressEvents)[0];
  }

  const meaningful = events.filter(event => event.type !== "PRINT_PROGRESS");
  const unique = new Map();

  for (const event of [...timeline.value, ...meaningful]) {
    unique.set(eventKey(event), event);
  }

  timeline.value = sortEvents([...unique.values()]).slice(0, 20);
}

async function refresh() {
  try {
    const response = await api("/api/status");

    data.value = {
      ...data.value,
      printer: response.printer || {},
      camera: response.camera || {},
      job: response.job || null
    };

    hydrateEvents(response.events || []);
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

function handleRealtimeEvent(event) {
  if (event.type === "PRINT_PROGRESS") {
    liveEvent.value = event;

    if (event.data) {
      data.value.printer = {
        ...data.value.printer,
        ...event.data
      };
    }

    return;
  }

  hydrateEvents([event]);

  if ([
    "PRINT_STARTED",
    "PRINT_FINISHED",
    "SNAPSHOT_SUCCESS",
    "SNAPSHOT_FAILED",
    "VIDEO_FINISHED"
  ].includes(event.type)) {
    refresh();
  }
}

function eventLabel(type) {
  const labels = {
    MQTT_CONNECTED: "MQTT",
    MQTT_DISCONNECTED: "MQTT",
    MQTT_PUSHALL: "SYNC",
    PRINT_STARTED: "START",
    LAYER_CHANGED: "LAYER",
    SNAPSHOT_STARTED: "CAPTURE",
    SNAPSHOT_SUCCESS: "CAPTURE",
    SNAPSHOT_FAILED: "ERROR",
    PRINT_COMPLETING: "FINISHING",
    PRINT_FINISHED: "FINISHED",
    VIDEO_STARTED: "VIDEO",
    VIDEO_FINISHED: "VIDEO",
    VIDEO_FAILED: "ERROR"
  };

  return labels[type] || type;
}

function eventTone(type) {
  if (["SNAPSHOT_SUCCESS", "VIDEO_FINISHED", "PRINT_FINISHED", "MQTT_CONNECTED"].includes(type)) {
    return "success";
  }

  if (["SNAPSHOT_FAILED", "VIDEO_FAILED", "MQTT_DISCONNECTED"].includes(type)) {
    return "danger";
  }

  if (["PRINT_STARTED", "LAYER_CHANGED", "SNAPSHOT_STARTED", "VIDEO_STARTED"].includes(type)) {
    return "active";
  }

  return "neutral";
}

onMounted(async () => {
  await refresh();
  socket = connectEvents(handleRealtimeEvent);
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
      <span class="badge" :class="statusClass">
        <i v-if="isRunning" class="live-dot"></i>
        {{ data.printer?.state || "IDLE" }}
      </span>
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

          <div class="progress">
            <i :style="{ width: progress + '%' }"></i>
          </div>
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

      <article class="card activity-card">
        <div class="card-title">
          <span>Activity</span>
          <span class="realtime-label">
            <i class="live-dot"></i>
            Realtime
          </span>
        </div>

        <div class="live-activity">
          <div class="activity-pulse" :class="{ running: isRunning }">
            <span></span>
          </div>

          <div class="live-copy">
            <small>Current state</small>
            <strong>
              {{ data.printer?.state || "Waiting" }}
              <template v-if="data.printer?.layer !== null && data.printer?.layer !== undefined">
                · Layer {{ data.printer.layer }}/{{ data.printer?.total_layers ?? "?" }}
              </template>
            </strong>
          </div>

          <div class="live-progress-copy">
            <small>Progress</small>
            <strong>{{ progress }}%</strong>
          </div>
        </div>

        <TransitionGroup name="event-list" tag="div" class="events">
          <div
            v-for="event in timeline"
            :key="eventKey(event)"
            class="event event-rich"
          >
            <span class="event-node" :class="eventTone(event.type)"></span>

            <div class="event-main">
              <span class="event-type" :class="eventTone(event.type)">
                {{ eventLabel(event.type) }}
              </span>
              <span class="event-message">{{ event.message }}</span>
            </div>

            <time>{{ new Date(event.time).toLocaleTimeString() }}</time>
          </div>
        </TransitionGroup>

        <div v-if="!timeline.length" class="empty event-empty">
          等待打印、换层、抓拍或视频生成事件…
        </div>
      </article>
    </template>
  </section>
</template>
