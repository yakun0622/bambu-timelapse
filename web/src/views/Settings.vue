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
        <p class="eyebrow">CONFIGURATION</p>
        <h1>Settings</h1>
        <p>当前配置来自 .env。敏感凭据不会返回到浏览器。</p>
      </div>
    </div>

    <div v-if="settings" class="grid two">
      <article class="card">
        <div class="card-title"><span>Bambu Cloud</span><span>MQTT</span></div>
        <dl>
          <dt>Host</dt><dd>{{ settings.bambu.mqtt_host }}:{{ settings.bambu.mqtt_port }}</dd>
          <dt>Device ID</dt><dd>{{ settings.bambu.device_id || "—" }}</dd>
          <dt>User ID</dt><dd>{{ settings.bambu.user_id_configured ? "Configured" : "Missing" }}</dd>
          <dt>Access Token</dt><dd>{{ settings.bambu.access_token_configured ? "Configured" : "Missing" }}</dd>
        </dl>
      </article>

      <article class="card">
        <div class="card-title"><span>Camera</span><span>Yi Hack</span></div>
        <dl>
          <dt>IP</dt><dd>{{ settings.camera.ip }}</dd>
          <dt>User</dt><dd>{{ settings.camera.user }}</dd>
          <dt>Password</dt><dd>{{ settings.camera.password_configured ? "Configured" : "Missing" }}</dd>
        </dl>
      </article>

      <article class="card">
        <div class="card-title"><span>Capture</span><span>Automation</span></div>
        <dl>
          <dt>Auto Capture</dt><dd>{{ settings.capture.auto_capture ? "On" : "Off" }}</dd>
          <dt>Delay</dt><dd>{{ settings.capture.snapshot_delay }} s</dd>
          <dt>Retries</dt><dd>{{ settings.capture.snapshot_retries }}</dd>
          <dt>Every</dt><dd>{{ settings.capture.capture_every_layers }} layer(s)</dd>
        </dl>
      </article>

      <article class="card">
        <div class="card-title"><span>Video</span><span>FFmpeg</span></div>
        <dl>
          <dt>Auto Generate</dt><dd>{{ settings.video.auto_generate_video ? "On" : "Off" }}</dd>
          <dt>FPS</dt><dd>{{ settings.video.fps }}</dd>
          <dt>Directory</dt><dd>{{ settings.video.directory }}</dd>
        </dl>
      </article>
    </div>
  </section>
</template>
