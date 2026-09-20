<script setup>
import { onMounted, ref } from "vue";
import { api } from "../api";

const jobs = ref([]);
const selected = ref(null);

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
  selected.value = await api(`/api/jobs/${job.id}`);
}

onMounted(load);
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

          <a
            v-if="selected.video_path"
            class="button link-button"
            :href="`/api/jobs/${selected.id}/video`"
          >
            下载延时视频
          </a>

          <div class="frame-grid">
            <img
              v-for="shot in selected.snapshots.filter(
                s => s.status === 'SUCCESS'
              )"
              :key="shot.id"
              :src="`/api/jobs/${selected.id}/frames/${shot.file_path.split('/').pop()}`"
              :title="`第 ${shot.layer} 层`"
            />
          </div>
        </template>

        <p v-else class="empty">
          请选择一个历史任务查看详情。
        </p>
      </article>
    </div>
  </section>
</template>
