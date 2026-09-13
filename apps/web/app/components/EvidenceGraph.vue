<script setup lang="ts">
const props = defineProps<{ cs: ReturnType<typeof useCase>; full?: boolean }>()
const v = computed(() => props.cs.evidence.value?.variant)
const verdict = computed(() => props.cs.verdict.value)
const met = computed(() => (verdict.value?.criteria ?? []).filter(c => !['NOT_MET', 'NOT_EVALUATED'].includes(c.status)))
const items = computed(() => {
  const all = props.cs.evidence.value?.evidence_items ?? []
  if (props.full) return all
  const used = new Set(met.value.flatMap(c => c.evidence_ids))
  const first = all.filter(e => used.has(e.id))
  return first.concat(all.filter(e => !used.has(e.id))).slice(0, 4)
})
const tone = computed(() => {
  const c = verdict.value?.classification ?? ''
  if (c.includes('Pathogenic')) return 'bg-red-50 border-red-200 text-red-700'
  if (c.includes('Benign')) return 'bg-green-50 border-green-200 text-green-700'
  return 'bg-gray-50 border-gray-200 text-gray-700'
})
const label = (t: string) => t.replace(/_/g, ' ')
</script>

<template>
  <div>
    <div class="grid grid-cols-[1fr_auto_1.4fr_auto_1.2fr_auto_1fr] gap-2 items-center text-[11px]">
      <div class="rounded-lg bg-indigo-50 border border-indigo-200 p-2 vc-mono text-center"><b>{{ v?.gene ?? '?' }}</b><br>{{ v?.hgvs ?? v?.input }}</div>
      <div class="text-gray-300 text-lg">→</div>
      <div class="space-y-1">
        <div v-for="e in items" :key="e.id" class="rounded-lg border border-gray-200 bg-white p-1.5" :title="e.summary">
          <div class="font-medium truncate">{{ e.source }}</div>
          <div class="text-gray-500 truncate">{{ label(e.evidence_type) }}<span v-if="e.transcript && v?.transcript && e.transcript !== v.transcript" class="text-amber-600"> · other transcript</span></div>
        </div>
        <div v-if="!items.length" class="text-gray-400">loading evidence…</div>
      </div>
      <div class="text-gray-300 text-lg">→</div>
      <div class="space-y-1">
        <div v-for="c in met" :key="c.code" class="rounded-lg border p-1.5" :class="c.code.startsWith('P') ? 'bg-red-50 border-red-200' : 'bg-green-50 border-green-200'">
          <b class="vc-mono">{{ c.code }}</b> <span class="text-gray-500">{{ c.status.toLowerCase().replace('_', ' ') }}</span>
          <div v-if="full" class="text-gray-500">{{ c.rationale }}</div>
        </div>
        <div v-if="!met.length" class="text-gray-400">{{ verdict ? 'no criteria met' : 'pending verdict' }}</div>
      </div>
      <div class="text-gray-300 text-lg">→</div>
      <div class="rounded-lg border p-2 text-center font-semibold" :class="verdict ? tone : 'bg-gray-50 border-gray-200 text-gray-400'">{{ verdict?.classification ?? '…' }}<div class="text-[10px] font-normal text-gray-500">ACMG classification</div></div>
    </div>
    <div class="grid grid-cols-[1fr_auto_1.4fr_auto_1.2fr_auto_1fr] text-[10px] text-gray-400 mt-2 text-center"><span>Variant</span><span /><span>Evidence ({{ cs.evidence.value?.evidence_items.length ?? 0 }} items)</span><span /><span>ACMG Criteria</span><span /><span>Conclusion</span></div>
  </div>
</template>
