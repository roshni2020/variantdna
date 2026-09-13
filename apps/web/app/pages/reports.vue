<script setup lang="ts">
const cs = useCaseRoute()
const v = computed(() => cs.evidence.value?.variant)
const verdict = computed(() => cs.verdict.value)
const met = computed(() => (verdict.value?.criteria ?? []).filter(c => !['NOT_MET', 'NOT_EVALUATED'].includes(c.status)))
function download() {
  const blob = new Blob([JSON.stringify({ case_id: cs.caseId.value, variant: v.value, verdict: verdict.value, rounds: cs.rounds.value.map(r => ({ round: r.round, pathogenic: r.pathogenic, benign: r.benign, cross_exam: r.crossExam, jury: r.jury, changes: r.result?.changes })), evidence: cs.evidence.value?.evidence_items, disclaimer: 'Research prototype - not for clinical diagnosis' }, null, 2)], { type: 'application/json' })
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `${cs.caseId.value}.json`; a.click()
}
</script>

<template>
  <div class="space-y-4 max-w-4xl">
    <section class="vc-card p-4 flex items-center gap-3">
      <div><h1 class="font-semibold text-lg">Reports</h1><div class="text-sm text-gray-500">Generate and export an analysis report for the current case.</div></div>
      <div class="ml-auto flex gap-2"><UButton variant="outline" @click="() => window.print()">Print / PDF</UButton><UButton color="primary" :disabled="!verdict" @click="download">Export JSON</UButton></div>
    </section>
    <section v-if="verdict" class="vc-card p-6 print:border-0">
      <div class="text-xs uppercase text-gray-500">VariantCourt case report</div>
      <h2 class="text-2xl font-semibold vc-mono mt-1">{{ v?.transcript }}<span v-if="v?.gene" class="text-gray-500">({{ v.gene }})</span>:{{ v?.hgvs }}</h2>
      <div class="text-sm text-gray-500">Case {{ cs.caseId.value }} · {{ new Date().toLocaleDateString() }} · {{ (cs.evidence.value?.sources_loaded ?? []).filter(s => s !== 'cache').join(', ') }}</div>
      <div class="mt-4 rounded-xl border-2 p-4 text-center text-2xl font-bold" :class="verdict.classification.includes('Pathogenic') ? 'border-red-300 text-red-700 bg-red-50' : verdict.classification.includes('Benign') ? 'border-green-300 text-green-700 bg-green-50' : 'border-gray-300 text-gray-700 bg-gray-50'">{{ verdict.classification }}</div>
      <div class="grid sm:grid-cols-3 gap-3 mt-4 text-sm">
        <div class="rounded-lg bg-gray-50 p-3"><div class="text-xs text-gray-500">Rounds</div><div class="font-semibold">{{ verdict.rounds_used }} · {{ verdict.converged ? 'converged' : 'cap reached' }}</div></div>
        <div class="rounded-lg bg-gray-50 p-3"><div class="text-xs text-gray-500">Human review</div><div class="font-semibold">{{ verdict.requires_human_review ? 'Required' : 'Not flagged' }}</div></div>
        <div class="rounded-lg bg-gray-50 p-3"><div class="text-xs text-gray-500">Unresolved conflicts</div><div class="font-semibold">{{ verdict.unresolved_conflicts.length }}</div></div>
      </div>
      <h3 class="font-semibold mt-5 mb-1">Criteria met</h3>
      <ul class="text-sm space-y-1"><li v-for="c in met" :key="c.code"><b class="vc-mono">{{ c.code }}</b> {{ c.status }} — {{ c.rationale }}</li><li v-if="!met.length" class="text-gray-500">none</li></ul>
      <h3 class="font-semibold mt-5 mb-1">Round summary</h3>
      <ol class="text-sm space-y-1 list-decimal ml-5"><li v-for="r in cs.rounds.value" :key="r.round">{{ r.pathogenic.length }} pathogenic and {{ r.benign.length }} benign claims; {{ r.crossExam?.rejected_claim_ids.length ?? 0 }} rejected by cross-examination; {{ r.result?.changes.length ?? 0 }} state changes.</li></ol>
      <h3 class="font-semibold mt-5 mb-1">Evidence</h3>
      <ul class="text-sm space-y-1"><li v-for="e in cs.evidence.value?.evidence_items ?? []" :key="e.id"><b>{{ e.source }}</b>: {{ e.summary }}</li></ul>
      <p class="mt-6 text-xs text-amber-700">{{ verdict.disclaimer }} Research prototype — not for clinical diagnosis.</p>
    </section>
    <p v-else class="text-sm text-gray-500">No completed case selected. Open one from the <NuxtLink to="/" class="text-indigo-600 underline">Dashboard</NuxtLink>.</p>
  </div>
</template>
