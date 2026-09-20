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

function stateLabel(value) {
  const labels = {
    RUNNING: "打印中",
    PRINTING: "打印中",
    PAUSE: "已暂停",
    PAUSED: "已暂停",
    FINISH: "已完成",
    FINISHED: "已完成",
    FAILED: "失败",
    CANCELED: "已取消",
    CANCEL: "已取消",
    IDLE: "空闲"
  };

  return labels[value] || value || "未知";
}

function eventKey(event) {
  if (event.id !== undefined && event.id !== null) {
    return `id:${event.id}`;
  }

  return [event.type, event.message, event.time].join("|");
}

function sortEvents(events) {
  return [...events].sort(
    (a, b) => new Date(b.time) - new Date(a.time)
  );
}

function hydrateEvents(events = []) {
  const progressEvents = events.filter(
    event => event.type === "PRINT_PROGRESS"
  );

  if (progressEvents.length) {
    liveEvent.value = sortEvents(progressEvents)[0];
  }

  const meaningful = events.filter(
    event => event.type !== "PRINT_PROGRESS"
  );

  const unique = new Map();

  for (const event of [...timeline.value, ...meaningful]) {
    unique.set(eventKey(event), event);
  }

  timeline.value = sortEvents(
    [...unique.values()]
  ).slice(0, 20);
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
    await api("/api/camera/snapshot", {
      method: "POST"
    });
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
    "PRINT_RESUMED",
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
    MQTT_CONNECTED: "连接",
    MQTT_DISCONNECTED: "连接",
    MQTT_PUSHALL: "同步",
    PRINT_STARTED: "开始",
    PRINT_RESUMED: "恢复",
    PRINT_IDENTIFIED: "识别",
    PRINT_INTERRUPTED: "中断",
    LAYER_CHANGED: "换层",
    SNAPSHOT_STARTED: "抓拍",
    SNAPSHOT_SUCCESS: "抓拍",
    SNAPSHOT_FAILED: "错误",
    PRINT_COMPLETING: "即将完成",
    PRINT_FINISHED: "完成",
    VIDEO_STARTED: "视频",
    VIDEO_FINISHED: "视频",
    VIDEO_FAILED: "错误",
    CONNECTED: "实时"
  };

  return labels[type] || type;
}

function eventMessage(event) {
  const d = event.data || {};

  switch (event.type) {
    case "MQTT_CONNECTED":
      return "Bambu MQTT 已连接";
    case "MQTT_DISCONNECTED":
      return "Bambu MQTT 已断开";
    case "MQTT_PUSHALL":
      return "已请求完整打印机状态";
    case "PRINT_STARTED":
      return "已开始新的打印任务";
    case "PRINT_RESUMED":
      return "已恢复未完成的打印任务";
    case "PRINT_IDENTIFIED":
      return "已识别当前 Bambu 打印任务";
    case "PRINT_INTERRUPTED":
      return "检测到新任务，旧任务已结束";
    case "LAYER_CHANGED":
      return d.layer ? `进入第 ${d.layer} 层` : "检测到换层";
    case "SNAPSHOT_STARTED":
      return d.layer ? `正在抓拍第 ${d.layer} 层` : "正在抓拍";
    case "SNAPSHOT_SUCCESS":
      return d.layer ? `第 ${d.layer} 层抓拍完成` : "抓拍完成";
    case "SNAPSHOT_FAILED":
      return d.layer ? `第 ${d.layer} 层抓拍失败` : "抓拍失败";
    case "PRINT_COMPLETING":
      return "打印进度已到 100%，等待完成状态";
    case "PRINT_FINISHED":
      return "打印任务已结束";
    case "VIDEO_STARTED":
      return "正在生成延时视频";
    case "VIDEO_FINISHED":
      return "延时视频生成完成";
    case "VIDEO_FAILED":
      return "延时视频生成失败";
    case "CONNECTED":
      return "实时连接已建立";
    default:
      return event.message;
  }
}

function eventTone(type) {
  if ([
    "SNAPSHOT_SUCCESS",
    "VIDEO_FINISHED",
    "PRINT_FINISHED",
    "MQTT_CONNECTED"
  ].includes(type)) {
    return "success";
  }

  if ([
    "SNAPSHOT_FAILED",
    "VIDEO_FAILED",
    "MQTT_DISCONNECTED"
  ].includes(type)) {
    return "danger";
  }

  if ([
    "PRINT_STARTED",
    "PRINT_RESUMED",
    "LAYER_CHANGED",
    "SNAPSHOT_STARTED",
    "VIDEO_STARTED"
  ].includes(type)) {
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
        <p class="eyebrow">实时状态</p>
        <h1>控制台</h1>
        <p>查看打印状态、摄像头和自动抓拍任务。</p>
      </div>

      <span class="badge" :class="statusClass">
        <i v-if="isRunning" class="live-dot"></i>
        {{ stateLabel(data.printer?.state) }}
      </span>
    </div>

    <div v-if="loading" class="card">正在加载…</div>

    <template v-else>
      <div class="grid two">
        <article class="card hero-card">
          <div class="card-title">
            <span>打印机</span>
            <span class="status-text">
              {{ stateLabel(data.printer?.state) }}
            </span>
          </div>

          <h2>Bambu Lab</h2>

          <div class="metric-row">
            <div>
              <small>打印进度</small>
              <strong>{{ progress }}%</strong>
            </div>

            <div>
              <small>当前层数</small>
              <strong>
                {{ data.printer?.layer ?? "—" }}
                /
                {{ data.printer?.total_layers ?? "—" }}
              </strong>
            </div>
          </div>

          <div class="progress">
            <i :style="{ width: progress + '%' }"></i>
          </div>
        </article>

        <article class="card">
          <div class="card-title">
            <span>小蚁摄像头</span>
            <span class="status-text">已配置</span>
          </div>

          <h2>{{ data.camera?.ip || "未配置" }}</h2>
          <p class="subtle">HTTP 高分辨率抓拍</p>
          <button class="button" @click="captureNow">
            立即抓拍
          </button>
        </article>
      </div>

      <article class="card current-job">
        <div class="card-title">
          <span>当前打印任务</span>
          <span>#{{ data.job?.id || "—" }}</span>
        </div>

        <div v-if="data.job" class="job-grid">
          <div>
            <small>任务名称</small>
            <strong>{{ data.job.name }}</strong>
          </div>
          <div>
            <small>任务状态</small>
            <strong>{{ stateLabel(data.job.status) }}</strong>
          </div>
          <div>
            <small>成功抓拍</small>
            <strong>{{ data.job.frame_count }}</strong>
          </div>
          <div>
            <small>失败抓拍</small>
            <strong>{{ data.job.failed_frames }}</strong>
          </div>
        </div>

        <p v-else class="empty">
          当前没有活动打印任务。
        </p>
      </article>

      <article class="card activity-card">
        <div class="card-title">
          <span>实时动态</span>
          <span class="realtime-label">
            <i class="live-dot"></i>
            实时
          </span>
        </div>

        <div class="live-activity">
          <div
            class="activity-pulse"
            :class="{ running: isRunning }"
          >
            <span></span>
          </div>

          <div class="live-copy">
            <small>当前状态</small>
            <strong>
              {{ stateLabel(data.printer?.state) }}
              <template
                v-if="
                  data.printer?.layer !== null &&
                  data.printer?.layer !== undefined
                "
              >
                · 第 {{ data.printer.layer }} /
                {{ data.printer?.total_layers ?? "?" }} 层
              </template>
            </strong>
          </div>

          <div class="live-progress-copy">
            <small>打印进度</small>
            <strong>{{ progress }}%</strong>
          </div>
        </div>

        <TransitionGroup
          name="event-list"
          tag="div"
          class="events"
        >
          <div
            v-for="event in timeline"
            :key="eventKey(event)"
            class="event event-rich"
          >
            <span
              class="event-node"
              :class="eventTone(event.type)"
            ></span>

            <div class="event-main">
              <span
                class="event-type"
                :class="eventTone(event.type)"
              >
                {{ eventLabel(event.type) }}
              </span>

              <span class="event-message">
                {{ eventMessage(event) }}
              </span>
            </div>

            <time>
              {{ new Date(event.time).toLocaleTimeString() }}
            </time>
          </div>
        </TransitionGroup>

        <div
          v-if="!timeline.length"
          class="empty event-empty"
        >
          等待打印、换层、抓拍或视频生成事件…
        </div>
      </article>
    </template>
  </section>
</template>
