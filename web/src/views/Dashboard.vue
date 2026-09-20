<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { api, connectEvents } from "../api";

const data = ref({
  printer: {},
  camera: {},
  job: null,
  latest_snapshot: null,
  events: []
});

const timeline = ref([]);
const loading = ref(true);
const cameraHealth = ref(null);
const testingCamera = ref(false);
const now = ref(Date.now());

let socket;
let refreshTimer;
let cameraTimer;
let clockTimer;

const progress = computed(() =>
  Number(data.value.printer?.progress || 0)
);

const isRunning = computed(() =>
  data.value.printer?.state === "RUNNING"
);

const printerOnline = computed(() =>
  Boolean(data.value.printer?.online)
);

const cameraOnline = computed(() =>
  Boolean(cameraHealth.value?.online)
);

const elapsedText = computed(() => {
  const startedAt = data.value.job?.started_at;

  if (!startedAt) return "—";

  const elapsedMs = Math.max(
    0,
    now.value - new Date(startedAt).getTime()
  );

  const totalSeconds = Math.floor(elapsedMs / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);

  if (hours > 0) {
    return `${hours}小时 ${minutes}分`;
  }

  return `${minutes}分钟`;
});

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
    INTERRUPTED: "已中断",
    IDLE: "空闲"
  };

  return labels[value] || value || "未知";
}

function eventKey(event) {
  return event.id !== undefined && event.id !== null
    ? `id:${event.id}`
    : [event.type, event.message, event.time].join("|");
}

function sortEvents(events) {
  return [...events].sort(
    (a, b) => new Date(b.time) - new Date(a.time)
  );
}

function hydrateEvents(events = []) {
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
      job: response.job || null,
      latest_snapshot: response.latest_snapshot || null
    };

    hydrateEvents(response.events || []);
  } finally {
    loading.value = false;
  }
}

async function testCamera() {
  if (testingCamera.value) return;

  testingCamera.value = true;

  try {
    cameraHealth.value = await api(
      "/api/camera/test",
      { method: "POST" }
    );
  } catch {
    cameraHealth.value = { online: false };
  } finally {
    testingCamera.value = false;
  }
}

async function captureNow() {
  try {
    await api(
      "/api/camera/snapshot",
      { method: "POST" }
    );

    setTimeout(refresh, 600);
  } catch (e) {
    alert(e.message);
  }
}

function handleRealtimeEvent(event) {
  if (event.type === "PRINT_PROGRESS") {
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
    "PRINT_IDENTIFIED",
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
  ].includes(type)) return "success";

  if ([
    "SNAPSHOT_FAILED",
    "VIDEO_FAILED",
    "MQTT_DISCONNECTED"
  ].includes(type)) return "danger";

  if ([
    "PRINT_STARTED",
    "PRINT_RESUMED",
    "LAYER_CHANGED",
    "SNAPSHOT_STARTED",
    "VIDEO_STARTED"
  ].includes(type)) return "active";

  return "neutral";
}

function formatTime(value) {
  return value
    ? new Date(value).toLocaleTimeString()
    : "—";
}

onMounted(async () => {
  await Promise.all([refresh(), testCamera()]);

  socket = connectEvents(handleRealtimeEvent);

  refreshTimer = setInterval(refresh, 15000);
  cameraTimer = setInterval(testCamera, 30000);
  clockTimer = setInterval(
    () => {
      now.value = Date.now();
    },
    1000
  );
});

onBeforeUnmount(() => {
  socket?.close();
  clearInterval(refreshTimer);
  clearInterval(cameraTimer);
  clearInterval(clockTimer);
});
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <p class="eyebrow">实时状态</p>
        <h1>控制台</h1>
        <p>查看设备状态、当前打印任务和最近抓拍。</p>
      </div>

      <span
        class="badge"
        :class="isRunning ? 'ok' : 'muted'"
      >
        <i v-if="isRunning" class="live-dot"></i>
        {{ stateLabel(data.printer?.state) }}
      </span>
    </div>

    <div v-if="loading" class="card">
      正在加载…
    </div>

    <template v-else>
      <div class="dashboard-primary-grid">
        <article class="card dashboard-primary-card printer-task-card">
          <div class="primary-card-head">
            <div>
              <small>拓竹打印机</small>
              <strong>Bambu Lab</strong>
            </div>

            <span
              class="connection-badge"
              :class="printerOnline ? 'online' : 'offline'"
            >
              <i></i>
              {{ printerOnline ? "在线" : "离线" }}
            </span>
          </div>

          <div class="printer-summary">
            <div>
              <small>打印状态</small>
              <strong>{{ stateLabel(data.printer?.state) }}</strong>
            </div>
            <div>
              <small>当前层数</small>
              <strong>
                {{ data.printer?.layer ?? "—" }}
                /
                {{ data.printer?.total_layers ?? "—" }}
              </strong>
            </div>
            <div>
              <small>打印进度</small>
              <strong>{{ progress }}%</strong>
            </div>
          </div>

          <div class="progress">
            <i :style="{ width: progress + '%' }"></i>
          </div>

          <div class="primary-divider"></div>

          <template v-if="data.job">
            <div class="job-inline-head">
              <div>
                <small>当前打印任务</small>
                <h2>{{ data.job.name }}</h2>
              </div>

              <span
                class="badge"
                :class="
                  data.job.status === 'PRINTING'
                    ? 'ok'
                    : data.job.status === 'PAUSED'
                      ? 'warn'
                      : 'muted'
                "
              >
                {{ stateLabel(data.job.status) }}
              </span>
            </div>

            <div class="job-inline-metrics">
              <div>
                <small>已运行</small>
                <strong>{{ elapsedText }}</strong>
              </div>
              <div>
                <small>成功抓拍</small>
                <strong>{{ data.job.frame_count }}</strong>
              </div>
              <div>
                <small>失败抓拍</small>
                <strong>{{ data.job.failed_frames }}</strong>
              </div>
              <div>
                <small>子任务 ID</small>
                <strong>{{ data.job.bambu_subtask_id || "—" }}</strong>
              </div>
            </div>

            <div class="task-key compact">
              <small>任务唯一键</small>
              <code>{{ data.job.job_key || "—" }}</code>
            </div>
          </template>

          <div v-else class="task-empty compact-empty">
            <div class="task-empty-icon">◌</div>
            <strong>当前没有活动打印任务</strong>
            <span>检测到打印开始后会自动创建并跟踪任务。</span>
          </div>
        </article>

        <article class="card dashboard-primary-card camera-snapshot-card">
          <div class="primary-card-head">
            <div>
              <small>小蚁摄像头</small>
              <strong>{{ data.camera?.ip || "未配置" }}</strong>
            </div>

            <span
              class="connection-badge"
              :class="cameraOnline ? 'online' : 'offline'"
            >
              <i></i>
              {{
                testingCamera
                  ? "检测中"
                  : cameraOnline
                    ? "在线"
                    : "离线"
              }}
            </span>
          </div>

          <div class="camera-summary">
            <div>
              <small>抓拍方式</small>
              <strong>HTTP 高分辨率</strong>
            </div>

            <div>
              <small>连接延迟</small>
              <strong>
                {{
                  cameraHealth?.duration_ms !== undefined
                    ? cameraHealth.duration_ms + " ms"
                    : "—"
                }}
              </strong>
            </div>

            <div class="camera-summary-actions">
              <button
                class="button secondary-button"
                :disabled="testingCamera"
                @click="testCamera"
              >
                检测连接
              </button>

              <button class="button" @click="captureNow">
                立即抓拍
              </button>
            </div>
          </div>

          <div class="primary-divider"></div>

          <div class="snapshot-inline-head">
            <div>
              <small>最近抓拍</small>
              <strong v-if="data.latest_snapshot">
                第 {{ data.latest_snapshot.layer }} 层
              </strong>
              <strong v-else>暂无抓拍</strong>
            </div>

            <span v-if="data.latest_snapshot" class="snapshot-time">
              {{ formatTime(data.latest_snapshot.captured_at) }}
            </span>
          </div>

          <template v-if="data.latest_snapshot">
            <div class="snapshot-preview merged">
              <img
                :src="
                  data.latest_snapshot.url
                  + '?v='
                  + data.latest_snapshot.id
                "
                :alt="`第 ${data.latest_snapshot.layer} 层抓拍`"
              />
            </div>

            <div class="snapshot-meta merged">
              <div>
                <small>抓拍层数</small>
                <strong>第 {{ data.latest_snapshot.layer }} 层</strong>
              </div>
              <div>
                <small>连接延迟</small>
                <strong>
                  {{
                    data.latest_snapshot.duration_ms !== null
                      ? data.latest_snapshot.duration_ms + " ms"
                      : "—"
                  }}
                </strong>
              </div>
              <div>
                <small>抓拍时间</small>
                <strong>{{ formatTime(data.latest_snapshot.captured_at) }}</strong>
              </div>
            </div>
          </template>

          <div v-else class="snapshot-empty merged-empty">
            <div class="snapshot-placeholder">
              <span>暂无抓拍</span>
            </div>
            <p>下一次自动抓拍成功后，图片会实时显示在这里。</p>
          </div>
        </article>
      </div>

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

        <div v-if="!timeline.length" class="empty event-empty">
          等待打印、换层、抓拍或视频生成事件…
        </div>
      </article>
    </template>
  </section>
</template>
