<script setup lang="ts">
const api = useApi()
const cfg = ref<any>(null)
onMounted(async () => { try { cfg.value = await api.get('/v1/config') } catch {} })
const rows = computed(() => cfg.value ? [
  ['Mode', cfg.value.mode === 'live' ? 'Live (LLM agents, deterministic fallback)' : 'Demo (deterministic agents)'],
  ['Max rounds', cfg.value.max_rounds],
  ['Evidence', cfg.value.evidence],
  ['Pathogenic Counsel', cfg.value.pathogenic],
  ['Benign Counsel', cfg.value.benign],
  ['Cross-Examiner', cfg.value.typesafe],
  ['Jury', cfg.value.jury],
  ['Tracer', cfg.value.tracer],
  ['LLM endpoint configured', cfg.value.llm_configured ? 'yes (W&B Inference on CoreWeave)' : 'no'],
  ['TypeSafe endpoint configured', cfg.value.typesafe_configured ? 'yes' : 'no (deterministic cross-examiner)'],
  ['Weave / W&B', cfg.value.weave_configured ? `${cfg.value.wandb_entity}/${cfg.value.wandb_project}` : 'off'],
  ['Research optimizer', cfg.value.aria],
] : [])
</script>

<template>
  <div class="space-y-4 max-w-3xl">
    <section class="vc-card p-4">
      <h1 class="font-semibold text-lg">Settings</h1>
      <p class="text-sm text-gray-500">Active configuration, read from the API. Change values in the <span class="vc-mono">.env</span> file and restart the backend.</p>
    </section>
    <section class="vc-card p-4">
      <table class="w-full text-sm"><tbody><tr v-for="[k, val] in rows" :key="k" class="border-t border-gray-100 first:border-0"><td class="py-2 text-gray-500 w-56">{{ k }}</td><td class="py-2 font-medium vc-mono">{{ val }}</td></tr></tbody></table>
      <p v-if="!cfg" class="text-sm text-gray-500">Backend not reachable on {{ api.base }}.</p>
    </section>
    <section class="vc-card p-4 text-sm text-gray-600">
      <h2 class="font-semibold text-gray-900 mb-1">Environment variables</h2>
      <ul class="vc-mono text-xs space-y-0.5"><li>VARIANTCOURT_MODE=live|demo</li><li>EVIDENCE_MODE=live|fixtures</li><li>MAX_ROUNDS=3</li><li>COREWEAVE_BASE_URL / COREWEAVE_MODEL</li><li>TYPESAFE_BASE_URL / TYPESAFE_API_KEY</li><li>WANDB_API_KEY / WANDB_ENTITY / WANDB_PROJECT</li></ul>
    </section>
  </div>
</template>
