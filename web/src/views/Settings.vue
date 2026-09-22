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
  bed_match_threshold: 0.78,
  bed_locator_mode: "aruco",
  aruco_id: 23,
  aruco_dictionary: "DICT_4X4_50",
  stable_px: 8,
  bed_stable_px: 8,
  stable_frames: 2,
  align_enabled: true,
  align_max_shift_px: 30,
  roi: { x: 700, y: 0, w: 580, h: 260 },
  target: { x: 760, y: 20, w: 180, h: 100 },
  bed_roi: { x: 0, y: 250, w: 1280, h: 470 },
  bed_target: { x: 0, y: 250, w: 1280, h: 470 }
});
const savingVision = ref(false);
const visionMessage = ref("");
const testingVision = ref(false);
const visionTestResult = ref(null);

const calibrationImage = ref(null);
const calibrationImageRef = ref(null);
const drawMode = ref("");
const drawing = ref(false);
const drawStart = ref(null);
const draftBox = ref(null);
const templateBox = ref({ x: 0, y: 0, w: 0, h: 0 });
const bedTemplateBox = ref({ x: 0, y: 0, w: 0, h: 0 });
const templateVersion = ref(Date.now());
const bedTemplateVersion = ref(Date.now());
const calibrationRenderVersion = ref(0);
const savingTemplate = ref(false);
const savingBedTemplate = ref(false);

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
    target: { ...settings.value.capture.vision_capture.target },
    bed_roi: { ...settings.value.capture.vision_capture.bed_roi },
    bed_target: { ...settings.value.capture.vision_capture.bed_target }
  };

  templateBox.value = {
    x: settings.value.capture.vision_capture.template?.x || 0,
    y: settings.value.capture.vision_capture.template?.y || 0,
    w: settings.value.capture.vision_capture.template?.w || 0,
    h: settings.value.capture.vision_capture.template?.h || 0
  };

  bedTemplateBox.value = {
    x: settings.value.capture.vision_capture.bed_template?.x || 0,
    y: settings.value.capture.vision_capture.bed_template?.y || 0,
    w: settings.value.capture.vision_capture.bed_template?.w || 0,
    h: settings.value.capture.vision_capture.bed_template?.h || 0
  };

  try {
    calibrationImage.value = await api(
      "/api/settings/vision-calibration-image"
    );
  } catch {
    calibrationImage.value = null;
  }
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

function imagePoint(event) {
  const image = calibrationImageRef.value;
  if (!image?.naturalWidth || !image?.naturalHeight) return null;

  const rect = image.getBoundingClientRect();
  const x = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
  const y = Math.max(0, Math.min(rect.height, event.clientY - rect.top));

  return {
    x: Math.round(x / rect.width * image.naturalWidth),
    y: Math.round(y / rect.height * image.naturalHeight)
  };
}

function boxStyle(box) {
  calibrationRenderVersion.value;
  const image = calibrationImageRef.value;
  if (!image?.naturalWidth || !image?.naturalHeight || !box?.w || !box?.h) {
    return { display: "none" };
  }

  return {
    left: (box.x / image.naturalWidth * 100) + "%",
    top: (box.y / image.naturalHeight * 100) + "%",
    width: (box.w / image.naturalWidth * 100) + "%",
    height: (box.h / image.naturalHeight * 100) + "%"
  };
}

function startDraw(mode) {
  drawMode.value = mode;
  draftBox.value = null;
}

function onCalibrationPointerDown(event) {
  if (!drawMode.value) return;

  const point = imagePoint(event);
  if (!point) return;

  drawing.value = true;
  drawStart.value = point;
  draftBox.value = {
    x: point.x,
    y: point.y,
    w: 0,
    h: 0
  };

  event.currentTarget.setPointerCapture?.(event.pointerId);
}

function onCalibrationPointerMove(event) {
  if (!drawing.value || !drawStart.value) return;

  const point = imagePoint(event);
  if (!point) return;

  const x = Math.min(drawStart.value.x, point.x);
  const y = Math.min(drawStart.value.y, point.y);
  const w = Math.abs(point.x - drawStart.value.x);
  const h = Math.abs(point.y - drawStart.value.y);

  draftBox.value = { x, y, w, h };
}

function onCalibrationPointerUp(event) {
  if (!drawing.value || !draftBox.value) return;

  drawing.value = false;

  const box = {
    x: Math.round(draftBox.value.x),
    y: Math.round(draftBox.value.y),
    w: Math.max(1, Math.round(draftBox.value.w)),
    h: Math.max(1, Math.round(draftBox.value.h))
  };

  if (drawMode.value === "roi") {
    visionCapture.value.roi = box;
  } else if (drawMode.value === "target") {
    visionCapture.value.target = box;
  } else if (drawMode.value === "template") {
    templateBox.value = box;
  } else if (drawMode.value === "bed_roi") {
    visionCapture.value.bed_roi = box;
  } else if (drawMode.value === "bed_target") {
    visionCapture.value.bed_target = box;
  } else if (drawMode.value === "bed_template") {
    bedTemplateBox.value = box;
  }

  draftBox.value = null;
  drawMode.value = "";
  event.currentTarget.releasePointerCapture?.(event.pointerId);
}

async function refreshCalibrationImage() {
  try {
    calibrationImage.value = await api(
      "/api/settings/vision-calibration-image"
    );
  } catch (error) {
    calibrationImage.value = null;
    visionMessage.value = error.message || "暂无标定图片";
  }
}

async function saveVisionTemplate() {
  if (!templateBox.value.w || !templateBox.value.h) {
    visionMessage.value = "请先在参考图上框选喷头模板";
    return;
  }

  savingTemplate.value = true;
  visionMessage.value = "";

  try {
    await api("/api/settings/vision-template", {
      method: "POST",
      body: JSON.stringify({
        snapshot_id: calibrationImage.value.snapshot_id,
        ...templateBox.value
      })
    });

    templateVersion.value = Date.now();
    visionMessage.value = "喷头模板已生成";
    await loadSettings();
  } catch (error) {
    visionMessage.value = error.message || "生成模板失败";
  } finally {
    savingTemplate.value = false;
  }
}

async function saveBedTemplate() {
  if (!bedTemplateBox.value.w || !bedTemplateBox.value.h) {
    visionMessage.value = "请先在参考图上框选热床锚点模板";
    return;
  }

  savingBedTemplate.value = true;
  visionMessage.value = "";

  try {
    await api("/api/settings/vision-bed-template", {
      method: "POST",
      body: JSON.stringify({
        snapshot_id: calibrationImage.value.snapshot_id,
        ...bedTemplateBox.value
      })
    });

    bedTemplateVersion.value = Date.now();
    visionMessage.value = "热床锚点模板已生成";
    await loadSettings();
  } catch (error) {
    visionMessage.value = error.message || "生成热床模板失败";
  } finally {
    savingBedTemplate.value = false;
  }
}

async function testVision() {
  testingVision.value = true;
  visionTestResult.value = null;
  visionMessage.value = "";

  try {
    // Ensure the backend tests the same parameters currently shown on screen.
    await saveVisionCapture();
    visionTestResult.value = await api("/api/settings/vision-test", {
      method: "POST"
    });
  } catch (error) {
    visionTestResult.value = {
      ok: false,
      reason: error.message || "视觉测试失败"
    };
  } finally {
    testingVision.value = false;
  }
}

async function saveVisionCapture() {
  savingVision.value = true;
  visionMessage.value = "";

  try {
    const payload = {
      lookback_ms: visionCapture.value.lookback_ms,
      match_threshold: visionCapture.value.match_threshold,
      bed_match_threshold: visionCapture.value.bed_match_threshold,
      bed_locator_mode: visionCapture.value.bed_locator_mode,
      aruco_id: visionCapture.value.aruco_id,
      aruco_dictionary: visionCapture.value.aruco_dictionary,
      stable_px: visionCapture.value.stable_px,
      bed_stable_px: visionCapture.value.bed_stable_px,
      stable_frames: visionCapture.value.stable_frames,
      align_enabled: visionCapture.value.align_enabled,
      align_max_shift_px: visionCapture.value.align_max_shift_px,
      roi_x: visionCapture.value.roi.x,
      roi_y: visionCapture.value.roi.y,
      roi_w: visionCapture.value.roi.w,
      roi_h: visionCapture.value.roi.h,
      target_x: visionCapture.value.target.x,
      target_y: visionCapture.value.target.y,
      target_w: visionCapture.value.target.w,
      target_h: visionCapture.value.target.h,
      bed_roi_x: visionCapture.value.bed_roi.x,
      bed_roi_y: visionCapture.value.bed_roi.y,
      bed_roi_w: visionCapture.value.bed_roi.w,
      bed_roi_h: visionCapture.value.bed_roi.h,
      bed_target_x: visionCapture.value.bed_target.x,
      bed_target_y: visionCapture.value.bed_target.y,
      bed_target_w: visionCapture.value.bed_target.w,
      bed_target_h: visionCapture.value.bed_target.h
    };

    const response = await api("/api/settings/vision-capture", {
      method: "PUT",
      body: JSON.stringify(payload)
    });

    visionCapture.value = {
      ...response.vision_capture,
      roi: { ...response.vision_capture.roi },
      target: { ...response.vision_capture.target },
      bed_roi: { ...response.vision_capture.bed_roi },
      bed_target: { ...response.vision_capture.bed_target }
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

          <dt class="capture-config-label">抓拍定位方式</dt>
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

                <button
                  type="button"
                  :class="{ active: captureTiming.mode === 'vision' }"
                  @click="captureTiming.mode = 'vision'"
                >
                  视觉定位
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
                v-else-if="captureTiming.mode === 'time'"
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


              <div
                v-else
                class="capture-config-input vision-mode-summary"
              >
                <label>视觉定位</label>
                <small>
                  从 RTSP 历史帧中同时识别喷头和热床锚点，只有两者都进入目标区域并连续稳定才会选中。
                  可按热床锚点自动平移对齐画面；如果没有找到符合条件的画面，会自动回退到“按时间”策略，
                  使用 {{ captureTiming.milliseconds }} ms。
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
              <span>喷头匹配阈值</span>
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
              <span>热床定位方式</span>
              <select
                v-model="visionCapture.bed_locator_mode"
                class="vision-select"
              >
                <option value="aruco">ArUco 标记</option>
                <option value="template">模板匹配</option>
              </select>
            </label>

            <label v-if="visionCapture.bed_locator_mode === 'aruco'">
              <span>ArUco Marker ID</span>
              <div class="capture-number-field">
                <input
                  v-model.number="visionCapture.aruco_id"
                  type="number"
                  min="0"
                  max="999"
                  step="1"
                />
              </div>
            </label>

            <label v-if="visionCapture.bed_locator_mode === 'aruco'">
              <span>ArUco 字典</span>
              <select
                v-model="visionCapture.aruco_dictionary"
                class="vision-select"
              >
                <option value="DICT_4X4_50">DICT_4X4_50</option>
                <option value="DICT_4X4_100">DICT_4X4_100</option>
                <option value="DICT_5X5_50">DICT_5X5_50</option>
              </select>
            </label>

            <label v-if="visionCapture.bed_locator_mode === 'template'">
              <span>热床匹配阈值</span>
              <div class="capture-number-field">
                <input
                  v-model.number="visionCapture.bed_match_threshold"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                />
              </div>
            </label>

            <label>
              <span>喷头稳定允许位移</span>
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
              <span>热床稳定允许位移</span>
              <div class="capture-number-field">
                <input
                  v-model.number="visionCapture.bed_stable_px"
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

            <label class="vision-align-toggle">
              <span>自动画面对齐</span>
              <div class="vision-toggle-line">
                <input
                  v-model="visionCapture.align_enabled"
                  type="checkbox"
                />
                <span>根据热床锚点进行平移校正</span>
              </div>
            </label>

            <label>
              <span>最大对齐位移</span>
              <div class="capture-number-field">
                <input
                  v-model.number="visionCapture.align_max_shift_px"
                  type="number"
                  min="0"
                  max="300"
                  step="1"
                />
                <span>px</span>
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

          <div class="vision-region-block">
            <div>
              <strong>热床定位搜索 ROI</strong>
              <small>
                ArUco 模式下只在这里寻找 Marker；模板模式下寻找热床锚点。
              </small>
            </div>

            <div class="vision-region-grid">
              <label><span>X</span><input v-model.number="visionCapture.bed_roi.x" type="number" min="0" /></label>
              <label><span>Y</span><input v-model.number="visionCapture.bed_roi.y" type="number" min="0" /></label>
              <label><span>W</span><input v-model.number="visionCapture.bed_roi.w" type="number" min="1" /></label>
              <label><span>H</span><input v-model.number="visionCapture.bed_roi.h" type="number" min="1" /></label>
            </div>
          </div>

          <div class="vision-region-block">
            <div>
              <strong>热床目标区域</strong>
              <small>
                Marker/热床锚点中心进入该区域后，才允许成为候选延时帧。
              </small>
            </div>

            <div class="vision-region-grid">
              <label><span>X</span><input v-model.number="visionCapture.bed_target.x" type="number" min="0" /></label>
              <label><span>Y</span><input v-model.number="visionCapture.bed_target.y" type="number" min="0" /></label>
              <label><span>W</span><input v-model.number="visionCapture.bed_target.w" type="number" min="1" /></label>
              <label><span>H</span><input v-model.number="visionCapture.bed_target.h" type="number" min="1" /></label>
            </div>
          </div>

          <div class="vision-calibration-block">
            <div class="vision-calibration-head">
              <div>
                <strong>画面标定</strong>
                <small>
                  直接拖框设置喷头与热床定位区域。ArUco 模式无需生成热床模板，只需让 ID 23 标记进入热床 ROI。
                </small>
              </div>

              <button
                type="button"
                class="button secondary-button"
                @click="refreshCalibrationImage"
              >
                刷新参考图
              </button>
            </div>

            <div
              v-if="calibrationImage"
              class="vision-calibration-stage"
              :class="{ drawing: drawMode }"
              @pointerdown="onCalibrationPointerDown"
              @pointermove="onCalibrationPointerMove"
              @pointerup="onCalibrationPointerUp"
              @pointercancel="onCalibrationPointerUp"
            >
              <img
                ref="calibrationImageRef"
                :src="calibrationImage.url + '?v=' + calibrationImage.snapshot_id"
                alt="视觉标定参考图"
                draggable="false"
                @load="calibrationRenderVersion++"
              />

              <div
                class="vision-box roi"
                :style="boxStyle(visionCapture.roi)"
              >
                <span>搜索 ROI</span>
              </div>

              <div
                class="vision-box target"
                :style="boxStyle(visionCapture.target)"
              >
                <span>目标区域</span>
              </div>

              <div
                class="vision-box template"
                :style="boxStyle(templateBox)"
              >
                <span>喷头模板</span>
              </div>

              <div
                class="vision-box bed-roi"
                :style="boxStyle(visionCapture.bed_roi)"
              >
                <span>热床 ROI</span>
              </div>

              <div
                class="vision-box bed-target"
                :style="boxStyle(visionCapture.bed_target)"
              >
                <span>热床目标</span>
              </div>

              <div
                v-if="visionCapture.bed_locator_mode === 'template'"
                class="vision-box bed-template"
                :style="boxStyle(bedTemplateBox)"
              >
                <span>热床模板</span>
              </div>

              <div
                v-if="draftBox"
                class="vision-box draft"
                :style="boxStyle(draftBox)"
              ></div>
            </div>

            <div v-else class="vision-calibration-empty">
              暂无抓拍图片。先完成一次抓拍，再回来进行视觉标定。
            </div>

            <div class="vision-calibration-tools">
              <button
                type="button"
                class="button secondary-button"
                :class="{ active: drawMode === 'roi' }"
                :disabled="!calibrationImage"
                @click="startDraw('roi')"
              >
                拖框搜索 ROI
              </button>

              <button
                type="button"
                class="button secondary-button"
                :class="{ active: drawMode === 'target' }"
                :disabled="!calibrationImage"
                @click="startDraw('target')"
              >
                拖框目标区域
              </button>

              <button
                type="button"
                class="button secondary-button"
                :class="{ active: drawMode === 'template' }"
                :disabled="!calibrationImage"
                @click="startDraw('template')"
              >
                框选喷头模板
              </button>

              <button
                type="button"
                class="button secondary-button"
                :class="{ active: drawMode === 'bed_roi' }"
                :disabled="!calibrationImage"
                @click="startDraw('bed_roi')"
              >
                拖框热床 ROI
              </button>

              <button
                type="button"
                class="button secondary-button"
                :class="{ active: drawMode === 'bed_target' }"
                :disabled="!calibrationImage"
                @click="startDraw('bed_target')"
              >
                拖框热床目标区
              </button>

              <button
                v-if="visionCapture.bed_locator_mode === 'template'"
                type="button"
                class="button secondary-button"
                :class="{ active: drawMode === 'bed_template' }"
                :disabled="!calibrationImage"
                @click="startDraw('bed_template')"
              >
                框选热床锚点
              </button>

              <button
                type="button"
                class="button"
                :disabled="savingTemplate || !templateBox.w"
                @click="saveVisionTemplate"
              >
                {{ savingTemplate ? "正在生成…" : "生成喷头模板" }}
              </button>
            </div>

            <div
              v-if="settings.capture.vision_capture.template?.configured"
              class="vision-template-preview"
            >
              <div>
                <small>当前喷头模板</small>
                <strong>
                  {{ settings.capture.vision_capture.template.w }}
                  ×
                  {{ settings.capture.vision_capture.template.h }}
                </strong>
              </div>

              <img
                :src="'/api/settings/vision-template?v=' + templateVersion"
                alt="喷头模板"
              />
            </div>

            <div
              v-if="visionCapture.bed_locator_mode === 'template'"
              class="vision-calibration-tools"
            >
              <button
                type="button"
                class="button"
                :disabled="savingBedTemplate || !bedTemplateBox.w"
                @click="saveBedTemplate"
              >
                {{ savingBedTemplate ? "正在生成…" : "生成热床锚点模板" }}
              </button>
            </div>

            <div
              v-else
              class="aruco-hint"
            >
              <strong>ArUco 热床定位已启用</strong>
              <span>
                当前使用 {{ visionCapture.aruco_dictionary }} /
                ID {{ visionCapture.aruco_id }}。把打印好的 Marker 固定在随热床移动且长期可见的位置即可。
              </span>

              <button
                type="button"
                class="button secondary-button vision-test-button"
                :disabled="testingVision"
                @click="testVision"
              >
                {{ testingVision ? "正在检测…" : "测试当前画面" }}
              </button>

              <div
                v-if="visionTestResult"
                class="vision-test-result"
                :class="{ ok: visionTestResult.ok }"
              >
                <strong>
                  {{ visionTestResult.ok ? "当前画面可用" : "当前画面未通过" }}
                </strong>
                <span>{{ visionTestResult.reason }}</span>

                <div v-if="visionTestResult.head" class="vision-test-grid">
                  <div>
                    <small>喷头</small>
                    <b>
                      {{
                        visionTestResult.head.detected
                          ? "已识别 " + (visionTestResult.head.score ?? "—")
                          : "未识别"
                      }}
                    </b>
                  </div>
                  <div>
                    <small>喷头目标区</small>
                    <b>{{ visionTestResult.head.in_target ? "是" : "否" }}</b>
                  </div>
                  <div>
                    <small>ArUco #{{ visionCapture.aruco_id }}</small>
                    <b>
                      {{
                        visionTestResult.bed?.detected
                          ? "已识别"
                          : "未识别"
                      }}
                    </b>
                  </div>
                  <div>
                    <small>热床目标区</small>
                    <b>{{ visionTestResult.bed?.in_target ? "是" : "否" }}</b>
                  </div>
                  <div>
                    <small>Marker 中心</small>
                    <b>
                      {{
                        visionTestResult.bed?.center_x !== null
                        && visionTestResult.bed?.center_x !== undefined
                          ? visionTestResult.bed.center_x
                            + ", "
                            + visionTestResult.bed.center_y
                          : "—"
                      }}
                    </b>
                  </div>
                  <div>
                    <small>Marker 尺寸</small>
                    <b>
                      {{
                        visionTestResult.bed?.marker_size_px
                          ? visionTestResult.bed.marker_size_px + " px"
                          : "—"
                      }}
                    </b>
                  </div>
                  <div>
                    <small>RTSP 帧龄</small>
                    <b>
                      {{
                        visionTestResult.frame_age_ms !== undefined
                          ? visionTestResult.frame_age_ms + " ms"
                          : "—"
                      }}
                    </b>
                  </div>
                </div>
              </div>
            </div>

            <div
              v-if="
                visionCapture.bed_locator_mode === 'template'
                && settings.capture.vision_capture.bed_template?.configured
              "
              class="vision-template-preview"
            >
              <div>
                <small>当前热床锚点模板</small>
                <strong>
                  {{ settings.capture.vision_capture.bed_template.w }}
                  ×
                  {{ settings.capture.vision_capture.bed_template.h }}
                </strong>
              </div>

              <img
                :src="'/api/settings/vision-bed-template?v=' + bedTemplateVersion"
                alt="热床锚点模板"
              />
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
