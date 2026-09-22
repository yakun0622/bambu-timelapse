<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { api } from "../api";

const jobs = ref([]);
const selected = ref(null);
const previewIndex = ref(0);
const previewPlaying = ref(false);
const previewFps = ref(5);
const previewLoop = ref(true);
const generatingVideo = ref(false);
const videoMessage = ref("");
const videoPreviewOpen = ref(false);

let previewTimer = null;
let refreshTimer = null;

const successShots = computed(() => {
  if (!selected.value?.snapshots) return [];

  return selected.value.snapshots
    .filter(shot => shot.status === "SUCCESS" && shot.file_path)
    .sort((a, b) => a.layer - b.layer);
});

const previewShot = computed(() =>
  successShots.value[previewIndex.value] || null
);

const previewProgress = computed(() => {
  const total = successShots.value.length;
  if (!total) return 0;
  return ((previewIndex.value + 1) / total) * 100;
});

const debugGroups = computed(() => {
  const rows = selected.value?.debug_snapshots || [];
  const grouped = new Map();

  for (const shot of rows) {
    if (!grouped.has(shot.layer)) grouped.set(shot.layer, []);
    grouped.get(shot.layer).push(shot);
  }

  return [...grouped.entries()]
    .sort((a, b) => b[0] - a[0])
    .slice(0, 8)
    .map(([layer, shots]) => ({
      layer,
      shots: shots.sort((a, b) => b.rewind_ms - a.rewind_ms)
    }));
});

function frameUrl(shot) {
  if (!selected.value || !shot?.file_path) return "";
  const filename = shot.file_path.split("/").pop();
  return `/api/jobs/${selected.value.id}/frames/${filename}`;
}

function debugFrameUrl(shot) {
  if (!selected.value || !shot?.id) return "";
  return `/api/jobs/${selected.value.id}/debug-frames/${shot.id}`;
}

function statusLabel(value) {
  const labels = {
    PRINTING: "打印中",
    PAUSED: "已暂停",
    FINISHED: "已完成",
    FAILED: "失败",
    CANCELED: "已取消",
    INTERRUPTED: "已中断"
  };
  return labels[value] || value || "未知";
}

async function load() {
  jobs.value = await api("/api/jobs");
}

async function open(job) {
  stopPreview();
  videoPreviewOpen.value = false;
  selected.value = await api(`/api/jobs/${job.id}`);
  previewIndex.value = 0;
}

async function refreshSelected() {
  if (!selected.value) return;

  const currentId = selected.value.id;
  const latest = await api(`/api/jobs/${currentId}`);
  const oldLength = successShots.value.length;

  selected.value = latest;

  if (
    previewPlaying.value
    && successShots.value.length > oldLength
    && previewIndex.value >= oldLength - 1
  ) {
    previewIndex.value = Math.max(0, successShots.value.length - 1);
  } else if (previewIndex.value >= successShots.value.length) {
    previewIndex.value = Math.max(0, successShots.value.length - 1);
  }
}

function stopPreview() {
  previewPlaying.value = false;
  if (previewTimer) {
    clearInterval(previewTimer);
    previewTimer = null;
  }
}

function schedulePreview() {
  if (previewTimer) clearInterval(previewTimer);

  if (!previewPlaying.value || successShots.value.length < 2) {
    previewTimer = null;
    return;
  }

  const fps = Math.max(1, Math.min(30, Number(previewFps.value) || 5));

  previewTimer = setInterval(() => {
    const total = successShots.value.length;
    if (!total) return;

    if (previewIndex.value < total - 1) {
      previewIndex.value += 1;
      return;
    }

    if (previewLoop.value) {
      previewIndex.value = 0;
    } else {
      stopPreview();
    }
  }, Math.round(1000 / fps));
}

function togglePreview() {
  if (successShots.value.length < 2) return;
  previewPlaying.value = !previewPlaying.value;
  schedulePreview();
}

function restartPreview() {
  previewIndex.value = 0;
  previewPlaying.value = true;
  schedulePreview();
}

function previousFrame() {
  if (!successShots.value.length) return;
  stopPreview();
  previewIndex.value = Math.max(0, previewIndex.value - 1);
}

function nextFrame() {
  if (!successShots.value.length) return;
  stopPreview();
  previewIndex.value = Math.min(
    successShots.value.length - 1,
    previewIndex.value + 1
  );
}

function changeFps() {
  previewFps.value = Math.max(
    1,
    Math.min(30, Number(previewFps.value) || 5)
  );

  if (previewPlaying.value) schedulePreview();
}

function openVideoPreview() {
  if (!selected.value?.video_path) return;
  stopPreview();
  videoPreviewOpen.value = true;
}

function closeVideoPreview() {
  videoPreviewOpen.value = false;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function generateVideo() {
  if (!selected.value || successShots.value.length < 2) return;

  generatingVideo.value = true;
  videoMessage.value = "";

  try {
    const response = await api(
      `/api/jobs/${selected.value.id}/video/generate`,
      { method: "POST" }
    );

    videoMessage.value =
      `正在生成视频，共 ${response.frames} 张图片…`;

    for (let attempt = 0; attempt < 90; attempt += 1) {
      await sleep(2000);
      await refreshSelected();

      if (selected.value?.video_path) {
        videoMessage.value = "视频生成完成";
        return;
      }
    }

    videoMessage.value =
      "视频仍在后台生成，可稍后刷新任务查看";
  } catch (error) {
    videoMessage.value = error.message || "视频生成失败";
  } finally {
    generatingVideo.value = false;
  }
}

onMounted(async () => {
  await load();

  refreshTimer = setInterval(async () => {
    try {
      await load();
      if (
        selected.value
        && ["PRINTING", "PAUSED"].includes(selected.value.status)
      ) {
        await refreshSelected();
      }
    } catch {
      // Keep current UI state if polling temporarily fails.
    }
  }, 5000);
});

onBeforeUnmount(() => {
  stopPreview();
  videoPreviewOpen.value = false;
  clearInterval(refreshTimer);
});
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <p class="eyebrow">历史记录</p>
        <h1>打印任务</h1>
        <p>查看历史打印任务、抓拍图片和生成的视频。</p>
      </div>
    </div>

    <div class="grid jobs-layout">
      <div class="stack">
        <button
          v-for="job in jobs"
          :key="job.id"
          class="job-card"
          @click="open(job)"
        >
          <div>
            <strong>{{ job.name }}</strong>
            <small>
              {{ new Date(job.started_at).toLocaleString() }}
            </small>
          </div>

          <div class="job-meta">
            <span>{{ statusLabel(job.status) }}</span>
            <span>{{ job.frame_count }} 张</span>
          </div>
        </button>
      </div>

      <article class="card detail">
        <template v-if="selected">
          <div class="card-title">
            <span>{{ selected.name }}</span>
            <span>{{ statusLabel(selected.status) }}</span>
          </div>

          <div class="job-grid">
            <div>
              <small>层数</small>
              <strong>
                {{ selected.current_layer }}
                /
                {{ selected.total_layers }}
              </strong>
            </div>
            <div>
              <small>进度</small>
              <strong>{{ selected.progress ?? 0 }}%</strong>
            </div>
            <div>
              <small>成功抓拍</small>
              <strong>{{ selected.frame_count }}</strong>
            </div>
            <div>
              <small>失败抓拍</small>
              <strong>{{ selected.failed_frames }}</strong>
            </div>
          </div>

          <dl class="identity-list">
            <dt>任务 ID</dt>
            <dd>{{ selected.bambu_task_id || "—" }}</dd>

            <dt>子任务 ID</dt>
            <dd>{{ selected.bambu_subtask_id || "—" }}</dd>

            <dt>任务唯一键</dt>
            <dd>{{ selected.job_key || "—" }}</dd>
          </dl>

          <div class="job-action-row">
            <button
              v-if="selected.video_path"
              type="button"
              class="button"
              @click="openVideoPreview"
            >
              预览延时视频
            </button>

            <a
              v-if="selected.video_path"
              class="button link-button secondary-button"
              :href="`/api/jobs/${selected.id}/video`"
            >
              下载视频
            </a>

            <button
              v-else-if="successShots.length >= 2"
              type="button"
              class="button secondary-button"
              :disabled="generatingVideo"
              @click="generateVideo"
            >
              {{ generatingVideo ? "正在生成…" : "手动生成视频" }}
            </button>

            <span
              v-if="videoMessage"
              class="preview-note"
            >
              {{ videoMessage }}
            </span>

            <span
              v-else-if="!selected.video_path && successShots.length"
              class="preview-note"
            >
              视频尚未生成，可先使用照片延时预览
            </span>
          </div>

          <section
            v-if="successShots.length"
            class="timelapse-preview-card"
          >
            <div class="timelapse-preview-head">
              <div>
                <small>照片延时预览</small>
                <strong>
                  第 {{ previewShot?.layer ?? "—" }} 层
                  · {{ previewIndex + 1 }} / {{ successShots.length }}
                </strong>
              </div>

              <span class="preview-status">
                {{ previewPlaying ? "播放中" : "已暂停" }}
              </span>
            </div>

            <div class="timelapse-preview-stage">
              <img
                v-if="previewShot"
                :src="frameUrl(previewShot)"
                :alt="`第 ${previewShot.layer} 层延时预览`"
              />
            </div>

            <div class="timelapse-preview-progress">
              <i :style="{ width: previewProgress + '%' }"></i>
            </div>

            <div class="timelapse-preview-controls">
              <div class="preview-main-controls">
                <button
                  type="button"
                  class="button secondary-button preview-icon-button"
                  :disabled="previewIndex <= 0"
                  @click="previousFrame"
                >
                  上一帧
                </button>

                <button
                  type="button"
                  class="button preview-play-button"
                  :disabled="successShots.length < 2"
                  @click="togglePreview"
                >
                  {{ previewPlaying ? "暂停" : "播放" }}
                </button>

                <button
                  type="button"
                  class="button secondary-button preview-icon-button"
                  :disabled="previewIndex >= successShots.length - 1"
                  @click="nextFrame"
                >
                  下一帧
                </button>

                <button
                  type="button"
                  class="button secondary-button"
                  :disabled="successShots.length < 2"
                  @click="restartPreview"
                >
                  从头播放
                </button>
              </div>

              <div class="preview-options">
                <label>
                  <span>预览帧率</span>
                  <input
                    v-model.number="previewFps"
                    type="number"
                    min="1"
                    max="30"
                    step="1"
                    @change="changeFps"
                  />
                  <em>FPS</em>
                </label>

                <label class="preview-loop-option">
                  <input
                    v-model="previewLoop"
                    type="checkbox"
                  />
                  <span>循环播放</span>
                </label>
              </div>
            </div>

            <p class="preview-help">
              预览直接依次播放已抓拍照片，不生成临时视频；
              打印过程中每 5 秒自动同步新增照片。
            </p>
          </section>

          <section
            v-if="debugGroups.length"
            class="debug-capture-results"
          >
            <div class="debug-results-head">
              <div>
                <small>抓帧调试结果</small>
                <strong>对比 MQTT 触发前不同时间点的画面</strong>
              </div>
              <span>最近 {{ debugGroups.length }} 层</span>
            </div>

            <div
              v-for="group in debugGroups"
              :key="group.layer"
              class="debug-layer-group"
            >
              <div class="debug-layer-title">
                <strong>第 {{ group.layer }} 层</strong>
                <span>{{ group.shots.length }} 张候选帧</span>
              </div>

              <div class="debug-frame-grid">
                <figure
                  v-for="shot in group.shots"
                  :key="shot.id"
                  class="debug-frame-card"
                >
                  <img
                    :src="debugFrameUrl(shot)"
                    :alt="`第 ${group.layer} 层 -${shot.rewind_ms}ms`"
                  />
                  <figcaption>
                    <strong>-{{ shot.rewind_ms }} ms</strong>
                    <span>
                      实际
                      {{
                        shot.actual_before_trigger_ms !== null
                          ? "-" + shot.actual_before_trigger_ms + " ms"
                          : "—"
                      }}
                    </span>
                  </figcaption>
                </figure>
              </div>
            </div>
          </section>

          <div class="frame-grid">
            <img
              v-for="shot in successShots"
              :key="shot.id"
              :src="frameUrl(shot)"
              :title="`第 ${shot.layer} 层`"
              @click="
                stopPreview();
                previewIndex = successShots.findIndex(s => s.id === shot.id)
              "
            />
          </div>
        </template>

        <p v-else class="empty">
          请选择一个历史任务查看详情。
        </p>
      </article>
    </div>
    <div
      v-if="videoPreviewOpen && selected?.video_path"
      class="video-preview-modal"
      @click.self="closeVideoPreview"
    >
      <div class="video-preview-dialog">
        <div class="video-preview-dialog-head">
          <div>
            <small>延时视频预览</small>
            <strong>{{ selected.name }}</strong>
          </div>

          <button
            type="button"
            class="video-preview-close"
            aria-label="关闭视频预览"
            @click="closeVideoPreview"
          >
            ×
          </button>
        </div>

        <div class="video-preview-player">
          <video
            :src="`/api/jobs/${selected.id}/video`"
            controls
            autoplay
            playsinline
          ></video>
        </div>

        <div class="video-preview-dialog-actions">
          <span>
            {{ selected.frame_count }} 张抓拍 ·
            {{ selected.total_layers || "—" }} 层
          </span>

          <a
            class="button link-button"
            :href="`/api/jobs/${selected.id}/video`"
          >
            下载视频
          </a>
        </div>
      </div>
    </div>
  </section>
</template>
