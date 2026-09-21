<script setup>
import { onMounted, ref } from "vue";
import { api } from "../api";

const settings = ref(null);
const captureTiming = ref({
  mode: "time",
  frames: 5,
  milliseconds: 1000
});
const savingTiming = ref(false);
const timingMessage = ref("");

const debugCapture = ref({
  enabled: false,
  start_ms: 3000,
  end_ms: 0,
  interval_ms: 500
});
const savingDebug = ref(false);
const debugMessage = ref("");

const visionCapture = ref({
  lookback_ms: 6000,
  match_threshold: 0.78,
  stable_px: 8,
  stable_frames: 2,
  roi: { x: 700, y: 0, w: 580, h: 260 },
  target: { x: 760, y: 20, w: 450, h: 180 }
});
const savingVision = ref(false);
const visionMessage = ref("");

async function loadSettings() {
  settings.value = await api("/api/settings");

  captureTiming.value = {
    mode: settings.value.capture.capture_rewind_mode,
    frames: settings.value.capture.capture_rewind_frames,
    milliseconds: settings.value.capture.capture_rewind_ms
  };

  debugCapture.value = {
    ...settings.value.capture.debug_capture
  };

  visionCapture.value = {
    ...settings.value.capture.vision_capture,
    roi: { ...settings.value.capture.vision_capture.roi },
    target: { ...settings.value.capture.vision_capture.target }
  };
}

async function saveDebugCapture() {
  savingDebug.value = true;
  debugMessage.value = "";

  try {
    const response = await api("/api/settings/debug-capture", {
      method: "PUT",
      body: JSON.stringify(debugCapture.value)
    });

    debugCapture.value = response.debug_capture;
    debugMessage.value = "已保存，下一次换层立即生效";
    await loadSettings();
  } catch (error) {
    debugMessage.value = error.message || "保存失败";
  } finally {
    savingDebug.value = false;
  }
}

async function saveVisionCapture() {
  savingVision.value = true;
  visionMessage.value = "";

  try {
    const payload = {
      lookback_ms: visionCapture.value.lookback_ms,
      match_threshold: visionCapture.value.match_threshold,
      stable_px: visionCapture.value.stable_px,
      stable_frames: visionCapture.value.stable_frames,
      roi_x: visionCapture.value.roi.x,
      roi_y: visionCapture.value.roi.y,
      roi_w: visionCapture.value.roi.w,
      roi_h: visionCapture.value.roi.h,
      target_x: visionCapture.value.target.x,
      target_y: visionCapture.value.target.y,
      target_w: visionCapture.value.target.w,
      target_h: visionCapture.value.target.h
    };

    const response = await api("/api/settings/vision-capture", {
      method: "PUT",
      body: JSON.stringify(payload)
    });

    visionCapture.value = {
      ...response.vision_capture,
      roi: { ...response.vision_capture.roi },
      target: { ...response.vision_capture.target }
    };
    visionMessage.value = "视觉参数已保存";
    await loadSettings();
  } catch (error) {
    visionMessage.value = error.message || "保存失败";
  } finally {
    savingVision.value = false;
  }
}

async function saveCaptureTiming() {
  savingTiming.value = true;
  timingMessage.value = "";

  try {
    const response = await api("/api/settings/capture-timing", {
      method: "PUT",
      body: JSON.stringify(captureTiming.value)
    });

    captureTiming.value = response.capture_timing;
    timingMessage.value = "已保存，下一次自动抓拍立即生效";
    await loadSettings();
  } catch (error) {
    timingMessage.value = error.message || "保存失败";
  } finally {
    savingTiming.value = false;
  }
}

onMounted(loadSettings);
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <p class="eyebrow">系统配置</p>
        <h1>设置</h1>
        <p>基础配置来自 .env；抓拍回溯策略可在页面保存并立即生效。</p>
      </div>
    </div>

    <div v-if="settings" class="grid two">
      <article class="card">
        <div class="card-title">
          <span>Bambu Cloud</span>
          <span>MQTT</span>
        </div>

        <dl>
          <dt>服务器</dt>
          <dd>
            {{ settings.bambu.mqtt_host }}:
            {{ settings.bambu.mqtt_port }}
          </dd>

          <dt>设备 ID</dt>
          <dd>{{ settings.bambu.device_id || "—" }}</dd>

          <dt>用户 ID</dt>
          <dd>
            {{
              settings.bambu.user_id_configured
                ? "已配置"
                : "未配置"
            }}
          </dd>

          <dt>访问令牌</dt>
          <dd>
            {{
              settings.bambu.access_token_configured
                ? "已配置"
                : "未配置"
            }}
          </dd>
        </dl>
      </article>

      <article class="card">
        <div class="card-title">
          <span>小蚁摄像头</span>
          <span>Yi Hack</span>
        </div>

        <dl>
          <dt>IP 地址</dt>
          <dd>{{ settings.camera.ip }}</dd>

          <dt>用户名</dt>
          <dd>{{ settings.camera.user }}</dd>

          <dt>密码</dt>
          <dd>
            {{
              settings.camera.password_configured
                ? "已配置"
                : "未配置"
            }}
          </dd>

          <dt>抓拍来源</dt>
          <dd>
            {{
              settings.camera.capture_source === "auto"
                ? "RTSP 优先 / HTTP 回退"
                : settings.camera.capture_source.toUpperCase()
            }}
          </dd>

          <dt>RTSP 地址</dt>
          <dd>{{ settings.camera.rtsp_display_url }}</dd>

          <dt>RTSP 端口</dt>
          <dd>{{ settings.camera.rtsp_port }}</dd>

          <dt>RTSP 路径</dt>
          <dd>{{ settings.camera.rtsp_path }}</dd>
        </dl>
      </article>

      <article class="card">
        <div class="card-title">
          <span>自动抓拍</span>
          <span>自动化</span>
        </div>

        <dl>
          <dt>自动抓拍</dt>
          <dd>{{ settings.capture.auto_capture ? "开启" : "关闭" }}</dd>

          <dt>RTSP 缓冲帧率</dt>
          <dd>{{ settings.capture.rtsp_frame_rate }} FPS</dd>

          <dt>最大帧龄</dt>
          <dd>{{ settings.capture.rtsp_frame_max_age }} 秒</dd>

          <dt>历史帧缓存</dt>
          <dd>{{ settings.capture.rtsp_history_frames }} 帧</dd>

          <dt class="capture-config-label">自动抓拍回溯</dt>
          <dd class="capture-config-cell">
            <div class="capture-config-panel">
              <div class="capture-mode-switch">
                <button
                  type="button"
                  :class="{ active: captureTiming.mode === 'frame' }"
                  @click="captureTiming.mode = 'frame'"
                >
                  按帧回退
                </button>

                <button
                  type="button"
                  :class="{ active: captureTiming.mode === 'time' }"
                  @click="captureTiming.mode = 'time'"
                >
                  按时间回退
                </button>
              </div>

              <div
                v-if="captureTiming.mode === 'frame'"
                class="capture-config-input"
              >
                <label>回退帧数</label>
                <div class="capture-number-field">
                  <input
                    v-model.number="captureTiming.frames"
                    type="number"
                    min="0"
                    max="300"
                    step="1"
                  />
                  <span>帧</span>
                </div>
                <small>
                  当前 RTSP {{ settings.capture.rtsp_frame_rate }} FPS，
                  {{ captureTiming.frames }} 帧约等于
                  {{
                    Math.round(
                      captureTiming.frames
                      / settings.capture.rtsp_frame_rate
                      * 1000
                    )
                  }} ms。
                </small>
              </div>

              <div
                v-else
                class="capture-config-input"
              >
                <label>回退时间</label>
                <div class="capture-number-field">
                  <input
                    v-model.number="captureTiming.milliseconds"
                    type="number"
                    min="0"
                    max="30000"
                    step="50"
                  />
                  <span>ms</span>
                </div>
                <small>
                  从 MQTT 换层消息到达时间向前查找最接近的历史帧。
                </small>
              </div>

              <div class="capture-config-actions">
                <button
                  type="button"
                  class="button"
                  :disabled="savingTiming"
                  @click="saveCaptureTiming"
                >
                  {{ savingTiming ? "正在保存…" : "保存抓拍策略" }}
                </button>

                <span
                  v-if="timingMessage"
                  class="capture-config-message"
                >
                  {{ timingMessage }}
                </span>
              </div>
            </div>
          </dd>

          <dt class="capture-config-label">抓帧调试模式</dt>
          <dd class="capture-config-cell">
            <div class="capture-config-panel debug-capture-panel">
              <label class="debug-toggle-row">
                <input
                  v-model="debugCapture.enabled"
                  type="checkbox"
                />
                <span>
                  <strong>开启调试模式</strong>
                  <small>
                    每次换层额外保存一组历史帧，用于寻找喷头最佳位置。
                  </small>
                </span>
              </label>

              <div class="debug-grid">
                <label>
                  <span>最早回溯</span>
                  <div class="capture-number-field">
                    <input
                      v-model.number="debugCapture.start_ms"
                      type="number"
                      min="0"
                      max="30000"
                      step="100"
                    />
                    <span>ms</span>
                  </div>
                </label>

                <label>
                  <span>最晚回溯</span>
                  <div class="capture-number-field">
                    <input
                      v-model.number="debugCapture.end_ms"
                      type="number"
                      min="0"
                      max="30000"
                      step="100"
                    />
                    <span>ms</span>
                  </div>
                </label>

                <label>
                  <span>采样间隔</span>
                  <div class="capture-number-field">
                    <input
                      v-model.number="debugCapture.interval_ms"
                      type="number"
                      min="50"
                      max="5000"
                      step="50"
                    />
                    <span>ms</span>
                  </div>
                </label>
              </div>

              <p class="debug-preview-text">
                当前将采样：
                -{{ Math.max(debugCapture.start_ms, debugCapture.end_ms) }} ms
                到
                -{{ Math.min(debugCapture.start_ms, debugCapture.end_ms) }} ms，
                间隔 {{ debugCapture.interval_ms }} ms。
              </p>

              <div class="capture-config-actions">
                <button
                  type="button"
                  class="button"
                  :disabled="savingDebug"
                  @click="saveDebugCapture"
                >
                  {{ savingDebug ? "正在保存…" : "保存调试配置" }}
                </button>

                <span
                  v-if="debugMessage"
                  class="capture-config-message"
                >
                  {{ debugMessage }}
                </span>
              </div>
            </div>
          </dd>

          <dt>HTTP 失败重试</dt>
          <dd>{{ settings.capture.snapshot_retries }} 次</dd>

          <dt>抓拍间隔</dt>
          <dd>
            每 {{ settings.capture.capture_every_layers }} 层
          </dd>
        </dl>
      </article>

      <article class="card vision-settings-card">
        <div class="card-title">
          <span>视觉定位参数</span>
          <span>Vision</span>
        </div>

        <div class="vision-settings-body">
          <p class="vision-settings-note">
            这些参数会保存到数据库，后续视觉选帧直接读取，调整后无需修改 .env。
          </p>

          <div class="vision-basic-grid">
            <label>
              <span>历史搜索范围</span>
              <div class="capture-number-field">
                <input
                  v-model.number="visionCapture.lookback_ms"
                  type="number"
                  min="500"
                  max="30000"
                  step="100"
                />
                <span>ms</span>
              </div>
            </label>

            <label>
              <span>模板匹配阈值</span>
              <div class="capture-number-field">
                <input
                  v-model.number="visionCapture.match_threshold"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                />
              </div>
            </label>

            <label>
              <span>稳定允许位移</span>
              <div class="capture-number-field">
                <input
                  v-model.number="visionCapture.stable_px"
                  type="number"
                  min="0"
                  max="200"
                  step="1"
                />
                <span>px</span>
              </div>
            </label>

            <label>
              <span>连续稳定帧</span>
              <div class="capture-number-field">
                <input
                  v-model.number="visionCapture.stable_frames"
                  type="number"
                  min="1"
                  max="20"
                  step="1"
                />
                <span>帧</span>
              </div>
            </label>
          </div>

          <div class="vision-region-block">
            <div>
              <strong>搜索 ROI</strong>
              <small>只在这个区域内寻找喷头。</small>
            </div>

            <div class="vision-region-grid">
              <label>
                <span>X</span>
                <input v-model.number="visionCapture.roi.x" type="number" min="0" />
              </label>
              <label>
                <span>Y</span>
                <input v-model.number="visionCapture.roi.y" type="number" min="0" />
              </label>
              <label>
                <span>W</span>
                <input v-model.number="visionCapture.roi.w" type="number" min="1" />
              </label>
              <label>
                <span>H</span>
                <input v-model.number="visionCapture.roi.h" type="number" min="1" />
              </label>
            </div>
          </div>

          <div class="vision-region-block">
            <div>
              <strong>目标停靠区域</strong>
              <small>喷头进入这个区域时，才视为候选拍摄位置。</small>
            </div>

            <div class="vision-region-grid">
              <label>
                <span>X</span>
                <input v-model.number="visionCapture.target.x" type="number" min="0" />
              </label>
              <label>
                <span>Y</span>
                <input v-model.number="visionCapture.target.y" type="number" min="0" />
              </label>
              <label>
                <span>W</span>
                <input v-model.number="visionCapture.target.w" type="number" min="1" />
              </label>
              <label>
                <span>H</span>
                <input v-model.number="visionCapture.target.h" type="number" min="1" />
              </label>
            </div>
          </div>

          <div class="capture-config-actions">
            <button
              type="button"
              class="button"
              :disabled="savingVision"
              @click="saveVisionCapture"
            >
              {{ savingVision ? "正在保存…" : "保存视觉参数" }}
            </button>

            <span
              v-if="visionMessage"
              class="capture-config-message"
            >
              {{ visionMessage }}
            </span>
          </div>
        </div>
      </article>

      <article class="card">
        <div class="card-title">
          <span>延时视频</span>
          <span>FFmpeg</span>
        </div>

        <dl>
          <dt>自动生成</dt>
          <dd>
            {{
              settings.video.auto_generate_video
                ? "开启"
                : "关闭"
            }}
          </dd>

          <dt>视频帧率</dt>
          <dd>{{ settings.video.fps }} FPS</dd>

          <dt>保存目录</dt>
          <dd>{{ settings.video.directory }}</dd>
        </dl>
      </article>
    </div>
  </section>
</template>
