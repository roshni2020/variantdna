<script setup lang="ts">
const api = useApi()
const analysis = ref<any>(null)
const cfg = ref<any>(null)
const loading = ref(false)
const running = ref(false)
const pending = ref<string[]>([])
const error = ref<string | null>(null)

async function refresh() {
  loading.value = true
  try { analysis.value = await api.get('/v1/research/analysis') } catch (e: any) { error.value = e.message } finally { loading.value = false }
}

async function runExperiment(maxRounds?: number) {
  running.value = true
  error.value = null
  try {
    const r = await api.post<{ case_ids: string[] }>('/v1/research/experiment', { max_rounds: maxRounds ?? null })
    pending.value = r.case_ids
    while (pending.value.length) {
      await new Promise(res => setTimeout(res, 700))
      const still: string[] = []
      for (const id of pending.value) {
        const c = await api.get<any>(`/v1/cases/${id}`)
        if (!['completed', 'failed'].includes(c.status)) still.push(id)
      }
      pending.value = still
    }
    await refresh()
  } catch (e: any) { error.value = e.message } finally { running.value = false }
}

onMounted(async () => { refresh(); try { cfg.value = await api.get('/v1/config') } catch {} })
const rec = computed(() => analysis.value?.recommendation)
const stats = computed(() => rec.value?.evidence?.by_max_rounds ?? {})
</script>

<template>
  <div class="space-y-4 max-w-5xl">
    <section class="vc-card p-4">
      <header class="flex items-center gap-3 mb-3 flex-wrap">
        <h1 class="font-semibold tracking-wide text-gray-900">RESEARCH OPTIMIZER <span class="text-xs font-normal text-gray-500">ARIA · outer loop across runs</span></h1>
        <span v-if="analysis" class="text-xs text-gray-500 vc-mono">{{ analysis.optimizer }}</span>
        <UButton class="ml-auto" size="sm" variant="ghost" :loading="loading" @click="refresh">Refresh</UButton>
      </header>
      <div v-if="cfg?.wandb_url" class="mb-3 rounded border border-indigo-100 bg-indigo-50 p-3 text-sm">
        <div class="text-xs uppercase text-indigo-600 mb-1">CoreWeave ARIA in Weights &amp; Biases</div>
        <p class="text-gray-800">Every case is logged as a W&amp;B run with its config (max_rounds, typesafe_enabled, provider) and per-round metrics, plus a Weave trace per agent call. Open the project and click <b>Ask ARIA</b> to have ARIA compare configurations and propose the next experiment. The local analysis below is the same question answered offline.</p>
        <div class="mt-2 flex gap-3 text-xs">
          <a :href="cfg.wandb_url" target="_blank" class="text-indigo-600 underline">W&amp;B runs ↗</a>
          <a :href="cfg.weave_url" target="_blank" class="text-indigo-600 underline">Weave traces ↗</a>
        </div>
      </div>
      <p v-if="error" class="text-red-600 text-sm">{{ error }}</p>
      <div v-if="rec" class="space-y-3">
        <div class="text-sm text-gray-500">Runs analyzed: <span class="text-gray-900 font-semibold">{{ rec.runs_analyzed }}</span></div>
        <div class="grid md:grid-cols-2 gap-3 text-sm">
          <div class="rounded bg-gray-50 p-3"><div class="text-xs uppercase text-gray-500 mb-1">Observed result</div><p>{{ rec.observed }}</p></div>
          <div class="rounded bg-gray-50 p-3"><div class="text-xs uppercase text-gray-500 mb-1">Hypothesis</div><p>{{ rec.hypothesis }}</p></div>
          <div class="rounded bg-gray-50 p-3"><div class="text-xs uppercase text-gray-500 mb-1">Recommended experiment</div><p>{{ rec.recommended_experiment }}</p></div>
          <div class="rounded bg-gray-50 p-3"><div class="text-xs uppercase text-gray-500 mb-1">Expected improvement</div><p>{{ rec.expected_improvement }}</p></div>
        </div>
        <div class="flex gap-2 flex-wrap items-center">
          <UButton color="primary" :loading="running" :disabled="running" @click="runExperiment()">Run Recommended Experiment<span v-if="rec.recommended_config?.max_rounds"> (max_rounds = {{ rec.recommended_config.max_rounds }})</span></UButton>
          <UButton variant="outline" :disabled="running" @click="runExperiment(5)">Baseline: 5 rounds</UButton>
          <UButton variant="outline" :disabled="running" @click="runExperiment(3)">Baseline: 3 rounds</UButton>
          <span v-if="running" class="text-xs text-gray-500 vc-pulse">{{ pending.length }} cases running…</span>
        </div>
      </div>
    </section>

    <section v-if="Object.keys(stats).length" class="vc-card p-4">
      <h2 class="font-semibold tracking-wide text-gray-800 mb-2">BY CONFIGURATION</h2>
      <table class="w-full text-sm">
        <thead class="text-xs text-gray-500"><tr><th class="text-left">max_rounds</th><th>runs</th><th>rounds used</th><th>latency ms</th><th>open conflicts</th><th>open high</th><th>converged</th><th>needs review</th><th>citation validity</th></tr></thead>
        <tbody>
          <tr v-for="(s, k) in stats" :key="k" class="text-center border-t border-gray-100" :class="{ 'text-green-700 font-semibold': Number(k) === rec?.recommended_config?.max_rounds }">
            <td class="text-left vc-mono">{{ k }}</td><td>{{ s.runs }}</td><td>{{ s.rounds_used }}</td><td>{{ s.latency_ms }}</td><td>{{ s.unresolved_conflicts }}</td><td>{{ s.unresolved_high }}</td><td>{{ Math.round(s.converged_rate * 100) }}%</td><td>{{ Math.round(s.review_rate * 100) }}%</td><td>{{ s.citation_validity }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="analysis?.runs?.length" class="vc-card p-4">
      <h2 class="font-semibold tracking-wide text-gray-800 mb-2">RECENT RUNS</h2>
      <table class="w-full text-xs">
        <thead class="text-gray-500"><tr><th class="text-left">case</th><th class="text-left">variant</th><th>cfg</th><th>typesafe</th><th>rounds</th><th>result</th><th>open high</th><th>ms</th></tr></thead>
        <tbody>
          <tr v-for="r in [...analysis.runs].reverse()" :key="r.case_id" class="border-t border-gray-100 text-center">
            <td class="text-left vc-mono"><NuxtLink :to="{ path: '/', query: { case: r.case_id } }" class="underline decoration-dotted">{{ r.case_id }}</NuxtLink></td>
            <td class="text-left vc-mono">{{ r.variant }}</td><td>{{ r.max_rounds }}</td><td>{{ r.typesafe_enabled ? 'on' : 'off' }}</td><td>{{ r.rounds_used }}{{ r.converged ? '✓' : '' }}</td><td>{{ r.classification }}</td><td>{{ r.conflicts_unresolved_high }}</td><td>{{ r.latency_ms }}</td>
          </tr>
        </tbody>
      </table>
    </section>
    <p class="text-xs text-amber-700">Research prototype — not for clinical diagnosis.</p>
  </div>
</template>
