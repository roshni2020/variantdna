<script setup lang="ts">
const props = defineProps<{ cs: ReturnType<typeof useCase> }>()
const v = computed(() => props.cs.evidence.value?.variant)
const verdict = computed(() => props.cs.verdict.value)
const running = computed(() => props.cs.status.value === 'running')
const failed = computed(() => props.cs.status.value === 'failed')
const tone = computed(() => {
  const c = verdict.value?.classification ?? ''
  if (c.includes('Pathogenic')) return 'bg-red-100 text-red-700'
  if (c.includes('Benign')) return 'bg-green-100 text-green-700'
  if (c === 'NEEDS_REVIEW') return 'bg-amber-100 text-amber-800'
  return 'bg-gray-100 text-gray-700'
})
const cons = computed(() => props.cs.evidence.value?.evidence_items.find(e => e.id === 'ev_vep_consequence')?.metadata?.consequence as string | undefined)
const updated = computed(() => new Date().toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }))
</script>

<template>
  <section class="vc-card p-4 flex flex-wrap items-center gap-4">
    <div class="w-14 h-14 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center text-2xl">&#9878;</div>
    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-2 text-sm text-gray-500">
        Case <span class="vc-mono text-gray-800 font-medium">{{ cs.caseId.value }}</span>
        <span class="chip" :class="running ? 'bg-blue-100 text-blue-700' : failed ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'">{{ running ? 'Active' : failed ? 'Failed' : 'Closed' }}</span>
      </div>
      <div class="text-xl font-semibold vc-mono truncate">{{ v?.transcript ?? '' }}<span v-if="v?.gene" class="text-gray-500">({{ v.gene }})</span>:{{ v?.hgvs ?? v?.input }}
        <span v-if="cons" class="text-gray-500 text-base font-normal">({{ (cs.evidence.value?.evidence_items.find(e => e.id === 'ev_vep_consequence')?.metadata?.protein_change as string) ?? '' }})</span>
      </div>
      <div class="text-sm text-gray-500 flex flex-wrap gap-x-3 mt-0.5">
        <span>Gene <b class="text-gray-800">{{ v?.gene ?? '?' }}</b></span>
        <span>Transcript <b class="text-gray-800 vc-mono">{{ v?.transcript ?? '?' }}</b></span>
        <span v-if="cons">Variant type <b class="text-gray-800">{{ cons.replace(/_/g, ' ') }}</b></span>
        <span v-if="cs.evidence.value?.disease_context?.disease_name">Disease context <b class="text-gray-800">{{ cs.evidence.value.disease_context.disease_name }}</b></span>
      </div>
    </div>
    <div v-if="verdict" class="chip text-sm px-3 py-1.5 font-semibold" :class="tone">{{ verdict.classification }}</div>
    <div v-else-if="failed" class="chip bg-red-100 text-red-700 text-sm px-3 py-1.5">Run failed</div>
    <div v-else class="chip bg-gray-100 text-gray-600 text-sm px-3 py-1.5 vc-pulse">Deliberating</div>
    <div class="grid grid-cols-3 gap-5 text-sm border-l border-gray-200 pl-5">
      <div><div class="text-gray-500">Sources</div><div class="font-semibold">▣ {{ cs.evidence.value?.evidence_items.length ?? 0 }}</div></div>
      <div><div class="text-gray-500">Last updated</div><div class="font-semibold">{{ updated }}</div></div>
      <div><div class="text-gray-500">Owner</div><div class="font-semibold">Roshni</div></div>
    </div>
  </section>
</template>
