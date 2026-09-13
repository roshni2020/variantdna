<script setup lang="ts">
const cs = useCaseRoute()
const groups = computed(() => {
  const g: Record<string, any[]> = {}
  for (const e of cs.evidence.value?.evidence_items ?? []) (g[e.source] ??= []).push(e)
  return g
})
const info: Record<string, { what: string; url: string }> = {
  'ClinVar': { what: 'NIH archive of clinical variant classifications with review status.', url: 'https://www.ncbi.nlm.nih.gov/clinvar/' },
  'Ensembl VEP': { what: 'Predicts the molecular consequence of a variant on each transcript.', url: 'https://www.ensembl.org/vep' },
  'gnomAD': { what: 'Population allele frequencies from over 800,000 people.', url: 'https://gnomad.broadinstitute.org/' },
  'gnomAD (via VEP)': { what: 'gnomAD frequencies as embedded in the Ensembl VEP response.', url: 'https://gnomad.broadinstitute.org/' },
  'Europe PMC': { what: 'Literature index; papers mentioning the variant.', url: 'https://europepmc.org/' },
}
</script>

<template>
  <div class="space-y-4">
    <CaseHeader v-if="cs.evidence.value" :cs="cs" />
    <section class="vc-card p-4">
      <h1 class="font-semibold text-lg">Sources</h1>
      <p class="text-sm text-gray-500">Where the evidence came from for this case, and what each source contributed. Loaded: {{ (cs.evidence.value?.sources_loaded ?? []).filter(s => s !== 'cache').join(', ') || '—' }}<span v-if="cs.evidence.value?.sources_loaded.includes('cache')"> (served from local cache)</span>.</p>
    </section>
    <section v-for="(items, src) in groups" :key="src" class="vc-card p-4">
      <header class="flex items-center gap-3 mb-2"><h2 class="font-semibold">{{ src }}</h2><span class="chip bg-indigo-50 text-indigo-700">{{ items.length }} item{{ items.length === 1 ? '' : 's' }}</span><a v-if="info[src]" :href="info[src].url" target="_blank" class="ml-auto text-xs text-indigo-600 underline">{{ info[src].url }}</a></header>
      <p v-if="info[src]" class="text-xs text-gray-500 mb-2">{{ info[src].what }}</p>
      <ul class="text-sm space-y-1.5">
        <li v-for="e in items" :key="e.id" class="flex gap-2"><span class="chip shrink-0" :class="e.direction === 'pathogenic' ? 'bg-red-100 text-red-700' : e.direction === 'benign' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'">{{ e.direction }}</span><span>{{ e.summary }} <a v-if="e.source_url" :href="e.source_url" target="_blank" class="text-indigo-600 text-xs">open ↗</a></span></li>
      </ul>
    </section>
    <p v-if="!cs.evidence.value" class="text-sm text-gray-500">Open a case from the <NuxtLink to="/" class="text-indigo-600 underline">Dashboard</NuxtLink> first.</p>
  </div>
</template>
