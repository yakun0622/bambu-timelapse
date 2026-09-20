<script setup>
import { onMounted, ref } from "vue";
import { api } from "../api";

const settings = ref(null);

onMounted(async () => {
  settings.value = await api("/api/settings");
});
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <p class="eyebrow">系统配置</p>
        <h1>设置</h1>
        <p>当前配置来自 .env，敏感凭据不会返回到浏览器。</p>
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

          <dt>抓拍延迟</dt>
          <dd>{{ settings.capture.snapshot_delay }} 秒</dd>

          <dt>RTSP 超时</dt>
          <dd>{{ settings.capture.rtsp_capture_timeout }} 秒</dd>

          <dt>RTSP 缓冲帧率</dt>
          <dd>{{ settings.capture.rtsp_frame_rate }} FPS</dd>

          <dt>最大帧龄</dt>
          <dd>{{ settings.capture.rtsp_frame_max_age }} 秒</dd>

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
