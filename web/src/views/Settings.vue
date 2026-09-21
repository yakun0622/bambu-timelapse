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

async function loadSettings() {
  settings.value = await api("/api/settings");

  captureTiming.value = {
    mode: settings.value.capture.capture_rewind_mode,
    frames: settings.value.capture.capture_rewind_frames,
    milliseconds: settings.value.capture.capture_rewind_ms
  };
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

          <dt>HTTP 失败重试</dt>
          <dd>{{ settings.capture.snapshot_retries }} 次</dd>

          <dt>抓拍间隔</dt>
          <dd>
            每 {{ settings.capture.capture_every_layers }} 层
          </dd>
        </dl>
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
