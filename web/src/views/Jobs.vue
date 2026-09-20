<script setup>
import { onMounted, ref } from "vue";
import { api } from "../api";

const jobs = ref([]);
const selected = ref(null);

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
        <p class="eyebrow">HISTORY</p>
        <h1>Jobs</h1>
        <p>查看历史任务、抓拍帧和生成的视频。</p>
      </div>
    </div>

    <div class="grid jobs-layout">
      <div class="stack">
        <button v-for="job in jobs" :key="job.id" class="job-card" @click="open(job)">
          <div>
            <strong>{{ job.name }}</strong>
            <small>{{ new Date(job.started_at).toLocaleString() }}</small>
          </div>
          <div class="job-meta">
            <span>{{ job.status }}</span>
            <span>{{ job.frame_count }} frames</span>
          </div>
        </button>
      </div>

      <article class="card detail">
        <template v-if="selected">
          <div class="card-title"><span>{{ selected.name }}</span><span>{{ selected.status }}</span></div>
          <div class="job-grid">
            <div><small>Layer</small><strong>{{ selected.current_layer }} / {{ selected.total_layers }}</strong></div>
            <div><small>Progress</small><strong>{{ selected.progress ?? 0 }}%</strong></div>
            <div><small>Frames</small><strong>{{ selected.frame_count }}</strong></div>
            <div><small>Failed</small><strong>{{ selected.failed_frames }}</strong></div>
          </div>

          <dl class="identity-list">
            <dt>Task ID</dt><dd>{{ selected.bambu_task_id || "—" }}</dd>
            <dt>Subtask ID</dt><dd>{{ selected.bambu_subtask_id || "—" }}</dd>
            <dt>Job Key</dt><dd>{{ selected.job_key || "—" }}</dd>
          </dl>
          <a v-if="selected.video_path" class="button link-button" :href="`/api/jobs/${selected.id}/video`">Download MP4</a>
          <div class="frame-grid">
            <img
              v-for="shot in selected.snapshots.filter(s => s.status === 'SUCCESS')"
              :key="shot.id"
              :src="`/api/jobs/${selected.id}/frames/${shot.file_path.split('/').pop()}`"
              :title="`Layer ${shot.layer}`"
            />
          </div>
        </template>
        <p v-else class="empty">选择一个历史任务查看详情。</p>
      </article>
    </div>
  </section>
</template>
