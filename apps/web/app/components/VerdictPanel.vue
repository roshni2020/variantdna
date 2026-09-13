<script setup lang="ts">
import type { Verdict } from '~/composables/useApi'
const props = defineProps<{ verdict: Verdict; sources: string[] }>()
const met = computed(() => props.verdict.criteria.filter(c => !['NOT_MET', 'NOT_EVALUATED'].includes(c.status)))
const pathMet = computed(() => met.value.filter(c => c.code.startsWith('P')))
const benMet = computed(() => met.value.filter(c => c.code.startsWith('B')))
const tone = computed(() => {
  const c = props.verdict.classification
  if (c.includes('Pathogenic')) return 'text-red-700 border-red-300 bg-red-50'
  if (c.includes('Benign')) return 'text-green-700 border-green-300 bg-green-50'
  if (c === 'NEEDS_REVIEW') return 'text-amber-800 border-amber-300 bg-amber-50'
  return 'text-gray-800 border-gray-500/50'
})
</script>

<template>
  <section class="vc-card p-4">
    <h2 class="font-semibold tracking-wide text-gray-800 mb-3">FINAL VERDICT <span class="text-xs font-normal text-gray-500">deterministic rule engine</span></h2>
    <div class="border-2 rounded-xl px-4 py-5 text-3xl font-bold text-center tracking-wide" :class="tone">{{ verdict.classification }}</div>
    <div class="grid sm:grid-cols-2 gap-3 mt-3 text-sm">
      <div>
        <div class="text-xs uppercase text-red-600 mb-1">Supporting criteria</div>
        <ul v-if="pathMet.length" class="space-y-1"><li v-for="c in pathMet" :key="c.code"><span class="vc-mono font-bold">{{ c.code }}</span> <span class="text-gray-500">{{ c.status }}</span><div class="text-xs text-gray-500">{{ c.rationale }}</div></li></ul>
        <p v-else class="text-gray-500">none</p>
      </div>
      <div>
        <div class="text-xs uppercase text-green-600 mb-1">Benign criteria</div>
        <ul v-if="benMet.length" class="space-y-1"><li v-for="c in benMet" :key="c.code"><span class="vc-mono font-bold">{{ c.code }}</span> <span class="text-gray-500">{{ c.status }}</span><div class="text-xs text-gray-500">{{ c.rationale }}</div></li></ul>
        <p v-else class="text-gray-500">none</p>
      </div>
    </div>
    <dl class="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-3 text-sm">
      <div><dt class="text-xs text-gray-500">Rounds used</dt><dd>{{ verdict.rounds_used }} <span class="text-xs text-gray-500">{{ verdict.converged ? 'converged' : 'cap reached' }}</span></dd></div>
      <div><dt class="text-xs text-gray-500">Unresolved conflicts</dt><dd>{{ verdict.unresolved_conflicts.length }}</dd></div>
      <div><dt class="text-xs text-gray-500">Human review</dt><dd :class="verdict.requires_human_review ? 'text-amber-700' : 'text-green-700'">{{ verdict.requires_human_review ? 'Required' : 'Not flagged' }}</dd></div>
      <div><dt class="text-xs text-gray-500">Sources</dt><dd class="text-xs">{{ sources.join(', ') }}</dd></div>
    </dl>
    <ul v-if="verdict.unresolved_conflicts.length" class="mt-2 text-xs text-gray-500 space-y-1">
      <li v-for="c in verdict.unresolved_conflicts" :key="c.id">• [{{ c.severity }}] {{ c.description }}</li>
    </ul>
    <p class="mt-3 text-xs text-amber-700/80">{{ verdict.disclaimer }} Research prototype — not for clinical diagnosis.</p>
  </section>
</template>
