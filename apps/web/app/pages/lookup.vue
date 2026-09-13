<script setup lang="ts">
const api = useApi()
const route = useRoute()
const q = ref(typeof route.query.variant === 'string' ? route.query.variant : 'NM_007294.4:c.68_69delAG')
const res = ref<any>(null)
const loading = ref(false)
const error = ref<string | null>(null)

async function look() {
  loading.value = true; error.value = null; res.value = null
  try { res.value = await api.get(`/v1/lookup?variant=${encodeURIComponent(q.value.trim())}`) } catch (e: any) { error.value = e.message } finally { loading.value = false }
}
onMounted(() => { if (route.query.variant) look() })

const dir = (d: string) => d === 'pathogenic' ? 'bg-red-100 text-red-700' : d === 'benign' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'
const freq = computed(() => {
  const af = res.value?.allele_frequency
  if (af == null) return 'no population data'
  if (af === 0) return 'never seen in population databases'
  return `about 1 in ${Math.round(1 / af).toLocaleString()} alleles (${(af * 100).toPrecision(2)}%)`
})
</script>

<template>
  <div class="space-y-4 max-w-4xl">
    <section class="vc-card p-4">
      <h1 class="font-semibold text-lg">Variant Lookup</h1>
      <p class="text-sm text-gray-600">What a DNA change is, in plain words, and which public sources confirm it. No verdict; that is the courtroom's job.</p>
      <form class="mt-3 flex gap-2" @submit.prevent="look">
        <input v-model="q" class="vc-mono flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm" placeholder="NM_007294.4:c.68_69delAG or rs80357914" />
        <UButton type="submit" color="primary" :loading="loading">Look up</UButton>
      </form>
      <p v-if="error" class="text-red-600 text-sm mt-2">{{ error }}</p>
    </section>

    <template v-if="res">
      <section class="vc-card p-4">
        <div class="flex flex-wrap items-start gap-4">
          <div class="flex-1 min-w-0">
            <div class="text-xs text-gray-500">Variant</div>
            <div class="text-xl font-semibold vc-mono">{{ res.transcript }}<span v-if="res.gene" class="text-gray-500">({{ res.gene }})</span>:{{ res.hgvs ?? res.input }}</div>
            <div class="text-sm text-gray-600 mt-1">
              <b>Gene {{ res.gene ?? 'unknown' }}</b>
              <span v-if="res.protein_change"> · protein change {{ res.protein_change }}</span>
              <span v-if="res.rsid"> · {{ res.rsid }}</span>
            </div>
          </div>
          <span v-if="res.clinvar_classification" class="chip px-3 py-1.5 text-sm font-semibold" :class="dir(res.clinvar_classification.toLowerCase().includes('pathogenic') ? 'pathogenic' : res.clinvar_classification.toLowerCase().includes('benign') ? 'benign' : 'neutral')">ClinVar: {{ res.clinvar_classification }}</span>
        </div>
        <dl class="grid sm:grid-cols-2 gap-3 mt-4 text-sm">
          <div class="rounded-lg bg-gray-50 p-3"><dt class="text-xs text-gray-500">What the change does</dt><dd class="capitalize-first">{{ res.what_it_does }} <span class="text-gray-400 vc-mono text-xs">({{ res.consequence }})</span></dd></div>
          <div class="rounded-lg bg-gray-50 p-3"><dt class="text-xs text-gray-500">How common it is</dt><dd>{{ freq }}</dd></div>
          <div class="rounded-lg bg-gray-50 p-3"><dt class="text-xs text-gray-500">Disease context</dt><dd>{{ res.disease_context ?? 'none recorded in ClinVar' }}</dd></div>
          <div class="rounded-lg bg-gray-50 p-3"><dt class="text-xs text-gray-500">Expert review</dt><dd>{{ res.clinvar_review ?? 'no ClinVar entry matched' }}</dd></div>
        </dl>
        <div class="mt-4 text-sm"><b>Confirmed by {{ res.sources_confirmed.length }} sources:</b> {{ res.sources_confirmed.join(', ') }}</div>
        <NuxtLink :to="{ path: '/', query: { variant: res.input } }" class="inline-block mt-3 text-sm text-indigo-600 underline">Put it on trial &rarr;</NuxtLink>
      </section>

      <section class="vc-card p-4">
        <h2 class="font-semibold mb-2">What each source says</h2>
        <table class="w-full text-sm">
          <thead class="text-xs text-gray-500 text-left"><tr><th>Source</th><th>Type</th><th>Finding</th><th>Leans</th><th></th></tr></thead>
          <tbody>
            <tr v-for="e in res.evidence" :key="e.id" class="border-t border-gray-100 align-top">
              <td class="py-2 font-medium whitespace-nowrap">{{ e.source }}</td>
              <td class="py-2 text-gray-500 whitespace-nowrap">{{ e.evidence_type.replace(/_/g, ' ') }}</td>
              <td class="py-2 text-gray-700">{{ e.summary }}<div v-if="e.transcript && e.transcript !== res.transcript" class="text-xs text-amber-700">annotated on {{ e.transcript }}, not the case transcript</div></td>
              <td class="py-2"><span class="chip" :class="dir(e.direction)">{{ e.direction }}</span></td>
              <td class="py-2"><a v-if="e.source_url" :href="e.source_url" target="_blank" class="text-indigo-600 underline text-xs">open ↗</a></td>
            </tr>
          </tbody>
        </table>
      </section>
      <p class="text-xs text-amber-700">{{ res.disclaimer }}</p>
    </template>
  </div>
</template>
