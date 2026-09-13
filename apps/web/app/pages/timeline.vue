<script setup lang="ts">
const cs = useCaseRoute()
</script>

<template>
  <div class="space-y-4">
    <CaseHeader v-if="cs.evidence.value" :cs="cs" />
    <div class="grid lg:grid-cols-[380px_1fr] gap-4">
      <section class="vc-card p-4">
        <h1 class="font-semibold text-lg mb-3">Deliberation Timeline</h1>
        <DeliberationTimeline :cs="cs" full />
      </section>
      <section class="vc-card p-4">
        <h2 class="font-semibold mb-3">Live transcript</h2>
        <div v-for="r in cs.rounds.value" :key="r.round" class="mb-4">
          <div class="text-sm font-semibold text-gray-700 mb-1">Round {{ r.round }}</div>
          <div class="space-y-1.5 text-sm">
            <div v-for="c in r.pathogenic" :key="c.id" class="rounded-lg bg-red-50 px-3 py-1.5"><b class="text-red-700">Pathogenic Counsel</b> <span class="vc-mono text-xs text-gray-500">{{ c.proposed_criterion || 'context' }} · {{ c.confidence.toFixed(2) }}<span v-if="c.rebuts"> · ↩ in reply to {{ c.rebuts }}</span></span><div>{{ c.claim }}</div></div>
            <div v-for="c in r.benign" :key="c.id" class="rounded-lg bg-green-50 px-3 py-1.5"><b class="text-green-700">Benign Counsel</b> <span class="vc-mono text-xs text-gray-500">{{ c.proposed_criterion || 'context' }} · {{ c.confidence.toFixed(2) }}<span v-if="c.rebuts"> · ↩ in reply to {{ c.rebuts }}</span></span><div>{{ c.claim }}</div></div>
            <div v-if="r.crossExam" class="rounded-lg bg-blue-50 px-3 py-1.5"><b class="text-blue-700">Cross-Examiner</b><ul class="list-disc ml-4"><li v-for="x in r.crossExam.contradictions" :key="x.id"><span class="uppercase text-[10px] text-gray-500">{{ x.severity }} {{ x.conflict_type.replace(/_/g, ' ') }}</span> {{ x.description }}</li><li v-if="!r.crossExam.contradictions.length">No contradictions found.</li></ul></div>
            <div v-if="r.jury" class="rounded-lg bg-amber-50 px-3 py-1.5"><b class="text-amber-800">Jury</b> {{ r.jury.rationale }}<ul class="text-xs text-gray-600 mt-1"><li v-for="d in r.jury.claim_decisions" :key="d.claim_id"><span class="uppercase">{{ d.action }}</span> <span class="vc-mono">{{ d.claim_id }}</span></li></ul></div>
            <div v-if="r.result" class="rounded-lg bg-gray-50 px-3 py-1.5 text-xs text-gray-600"><b>Clerk</b> {{ r.result.changes.length ? r.result.changes.join('; ') : 'No state changes.' }}<span v-if="r.stateAfter?.converged" class="text-green-700 font-semibold"> · CONVERGED</span></div>
          </div>
        </div>
        <p v-if="!cs.rounds.value.length" class="text-sm text-gray-500">Open a case from the <NuxtLink to="/" class="text-indigo-600 underline">Dashboard</NuxtLink> first.</p>
      </section>
    </div>
  </div>
</template>
