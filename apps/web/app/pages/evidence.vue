<script setup lang="ts">
const cs = useCaseRoute()
</script>

<template>
  <div class="space-y-4">
    <CaseHeader v-if="cs.evidence.value" :cs="cs" />
    <section class="vc-card p-4">
      <header class="mb-4"><h1 class="font-semibold text-lg">Evidence Graph</h1><div class="text-sm text-gray-500">From variant to evidence to ACMG criteria to conclusion. Evidence on a different transcript is shown but ignored by the rule engine.</div></header>
      <EvidenceGraph v-if="cs.evidence.value" :cs="cs" full />
      <p v-else class="text-sm text-gray-500">Open a case from the <NuxtLink to="/" class="text-indigo-600 underline">Dashboard</NuxtLink> first.</p>
    </section>
    <section v-if="cs.evidence.value" class="vc-card p-4">
      <h2 class="font-semibold mb-2">All evidence items</h2>
      <table class="w-full text-sm">
        <thead class="text-xs text-gray-500 text-left"><tr><th>ID</th><th>Source</th><th>Type</th><th>Summary</th><th>Leans</th><th>Conf.</th></tr></thead>
        <tbody>
          <tr v-for="e in cs.evidence.value.evidence_items" :key="e.id" class="border-t border-gray-100 align-top">
            <td class="py-1.5 vc-mono text-xs text-gray-500">{{ e.id }}</td><td class="py-1.5 whitespace-nowrap">{{ e.source }}</td><td class="py-1.5 text-gray-500 whitespace-nowrap">{{ e.evidence_type.replace(/_/g, ' ') }}</td>
            <td class="py-1.5 text-gray-700">{{ e.summary }} <a v-if="e.source_url" :href="e.source_url" target="_blank" class="text-indigo-600 text-xs">↗</a></td>
            <td class="py-1.5"><span class="chip" :class="e.direction === 'pathogenic' ? 'bg-red-100 text-red-700' : e.direction === 'benign' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'">{{ e.direction }}</span></td>
            <td class="py-1.5 vc-mono text-xs">{{ e.confidence.toFixed(2) }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>
