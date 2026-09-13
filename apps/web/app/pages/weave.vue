<script setup lang="ts">
const api = useApi()
const cfg = ref<any>(null)
const stats = ref<any>(null)
onMounted(async () => {
  try { cfg.value = await api.get('/v1/config') } catch {}
  try { stats.value = await api.get('/v1/stats') } catch {}
})
</script>

<template>
  <div class="space-y-4 max-w-3xl">
    <section class="vc-card p-4">
      <h1 class="font-semibold">Weave Traces</h1>
      <p class="text-sm text-gray-600 mt-1">Every case is one trace. Inside it, each agent call is a span with its inputs and outputs, and each round is a turn in the Agents view, so you can read the courtroom as a conversation.</p>
      <div class="mt-3 flex flex-wrap gap-2">
        <a v-if="cfg?.weave_url" :href="cfg.weave_url" target="_blank" class="chip bg-indigo-600 text-white px-3 py-1.5">Traces ↗</a>
        <a v-if="cfg?.weave_url" :href="cfg.weave_url + '/agents'" target="_blank" class="chip bg-indigo-100 text-indigo-700 px-3 py-1.5">Agents conversations ↗</a>
        <a v-if="cfg?.weave_url" :href="cfg.weave_url + '/evaluations'" target="_blank" class="chip bg-indigo-100 text-indigo-700 px-3 py-1.5">Evaluations ↗</a>
        <a v-if="cfg?.wandb_url" :href="cfg.wandb_url" target="_blank" class="chip bg-gray-100 text-gray-700 px-3 py-1.5">W&amp;B runs (ARIA) ↗</a>
      </div>
    </section>
    <section v-if="stats" class="vc-card p-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
      <div><div class="text-2xl font-semibold">{{ stats.completed }}</div><div class="text-gray-500">cases completed</div></div>
      <div><div class="text-2xl font-semibold">{{ stats.agent_calls }}</div><div class="text-gray-500">agent calls</div></div>
      <div><div class="text-2xl font-semibold">{{ (stats.avg_latency_ms / 1000).toFixed(1) }}s</div><div class="text-gray-500">avg latency</div></div>
      <div><div class="text-2xl font-semibold">{{ Math.round(stats.converged_rate * 100) }}%</div><div class="text-gray-500">converged</div></div>
    </section>
  </div>
</template>
