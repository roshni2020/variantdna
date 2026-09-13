<script setup lang="ts">
const props = defineProps<{ cs: ReturnType<typeof useCase>; full?: boolean }>()
const verdict = computed(() => props.cs.verdict.value)
const desc = (r: any) => r.round === 1 ? 'Initial arguments from all agents' : r.result?.changes.length ? 'Cross-examination and counterpoints' : 'Refined positions and convergence'
</script>

<template>
  <div>
    <ol class="relative border-l-2 border-indigo-100 ml-2 space-y-4">
      <li v-for="r in cs.rounds.value" :key="r.round" class="ml-4">
        <span class="absolute -left-[7px] w-3 h-3 rounded-full border-2 border-indigo-500 bg-white" />
        <div class="flex items-center gap-2"><b class="text-sm">Round {{ r.round }}</b><span class="ml-auto chip bg-indigo-50 text-indigo-700">{{ r.result ? `${r.result.changes.length} updates` : `${r.pathogenic.length + r.benign.length} claims` }}</span></div>
        <div class="text-xs text-gray-500">{{ desc(r) }}</div>
        <ul v-if="r.result && (full || r.result.changes.length)" class="mt-1 text-[11px] text-gray-600 space-y-0.5">
          <li v-for="ch in (full ? r.result.changes : r.result.changes.slice(0, 3))" :key="ch">• {{ ch }}</li>
          <li v-if="!full && r.result.changes.length > 3" class="text-gray-400">+{{ r.result.changes.length - 3 }} more</li>
        </ul>
        <div v-if="full && r.crossExam" class="mt-1 text-[11px] text-blue-700">Cross-examiner: {{ r.crossExam.rejected_claim_ids.length }} rejected, {{ r.crossExam.weakened_claim_ids.length }} weakened, {{ r.crossExam.contradictions.length }} findings</div>
        <div v-if="full && r.jury" class="mt-0.5 text-[11px] text-amber-800">Jury: {{ r.jury.rationale }}</div>
      </li>
      <li v-if="!cs.rounds.value.length" class="ml-4 text-sm text-gray-400">No rounds yet.</li>
    </ol>
    <div v-if="verdict" class="mt-4 rounded-lg p-3 text-sm flex items-center gap-3" :class="verdict.converged ? 'bg-green-50 text-green-800' : 'bg-amber-50 text-amber-800'">
      <span class="text-lg">{{ verdict.converged ? '◎' : '⚠' }}</span>
      <div><b>{{ verdict.converged ? 'Converged' : 'Round cap reached' }}</b><div class="text-xs">{{ verdict.converged ? 'Agents reached a stable conclusion' : 'Flagged for human review' }} · {{ verdict.rounds_used }} rounds</div></div>
    </div>
  </div>
</template>
