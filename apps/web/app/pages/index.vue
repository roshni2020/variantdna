<script setup lang="ts">
import type { Claim } from '~/composables/useApi'

const route = useRoute()
const cs = useCase()
const stats = ref<any>(null)
const rec = ref<any>(null)
const runningPlan = ref(false)

async function loadSide() {
  try { stats.value = await cs.api.get('/v1/stats') } catch {}
  try { rec.value = (await cs.api.get<any>('/v1/research/analysis')).recommendation } catch {}
}
onMounted(async () => {
  try { cs.config.value = await cs.api.get<any>('/v1/config') } catch {}
  loadSide()
  if (typeof route.query.case === 'string') cs.load(route.query.case)
  else if (typeof route.query.variant === 'string') cs.open(route.query.variant)
  else { try { const last = localStorage.getItem('vc:lastCase'); if (last) cs.load(last) } catch {} }
})
watch(() => [route.query.variant, route.query.t], ([v]) => { if (typeof v === 'string') cs.open(v) })
watch(() => cs.status.value, s => { if (s === 'completed') loadSide() })

const demoCards = [
  { v: 'NM_007294.4:c.68_69delAG', title: 'BRCA1 founder mutation', blurb: 'Well-known disease-causing change.' },
  { v: 'NM_007294.4:c.4837A>G', title: 'BRCA1 common variant', blurb: 'Carried by a third of people.' },
  { v: 'NM_000546.6:c.524G>A', title: 'TP53 hotspot', blurb: 'Real sources disagree; the court abstains.' },
  { v: 'BRAF V600E', title: 'BRAF V600E (plain name)', blurb: 'Clinician shorthand, resolved to transcript HGVS.' },
]
const cur = computed(() => cs.current.value)
const state = computed(() => cur.value?.stateAfter ?? cs.evidence.value)
const isRunning = computed(() => cs.status.value === 'running')

function conf(claims: Claim[]) {
  if (!claims.length) return 0
  // Use the reduced state: rejected claims are gone, weakened ones carry the jury's lowered confidence.
  const after = cur.value?.stateAfter
  const reduced = new Map((after ? [...after.pathogenic_claims, ...after.benign_claims] : []).map(c => [c.id, c.confidence]))
  const rej = new Set(cur.value?.crossExam?.rejected_claim_ids ?? [])
  const total = claims.reduce((a, c) => a + (rej.has(c.id) ? 0 : (after ? (reduced.get(c.id) ?? 0) : c.confidence)), 0)
  return Math.round((total / claims.length) * 100)
}
const pathConf = computed(() => conf(cur.value?.pathogenic ?? []))
const benConf = computed(() => conf(cur.value?.benign ?? []))
const xConf = computed(() => {
  const x = cur.value?.crossExam
  if (!x) return 0
  const total = x.validated_claim_ids.length + x.weakened_claim_ids.length + x.rejected_claim_ids.length
  return total ? Math.round(((x.rejected_claim_ids.length + x.weakened_claim_ids.length * 0.5) / total) * 100) : 0
})
const xBullets = computed(() => {
  const x = cur.value?.crossExam
  if (!x) return []
  const out = x.contradictions.slice(0, 4).map(c => c.description)
  if (!out.length) out.push('No contradictions found; all claims hold up against the evidence.')
  return out
})
const xChips = computed(() => [...new Set((cur.value?.crossExam?.contradictions ?? []).map(c => c.conflict_type.replace(/_/g, ' ')))].slice(0, 3))
const chips = (claims: Claim[]) => [...new Set(claims.map(c => c.proposed_criterion).filter(Boolean))] as string[]
const stepLabel: Record<string, string> = { pathogenic: 'Pathogenic Counsel arguing', benign: 'Benign Counsel arguing', typesafe: 'Cross-examining', jury: 'Jury deliberating', reducer: 'Recording state' }

async function runPlan() {
  runningPlan.value = true
  try { await cs.api.post('/v1/research/experiment', {}) } catch {} finally { setTimeout(() => { runningPlan.value = false; loadSide() }, 1500) }
}
const spark = computed(() => {
  const xs: number[] = stats.value?.recent_latency_ms ?? []
  if (xs.length < 2) return ''
  const max = Math.max(...xs), w = 300, h = 70
  return xs.map((y, i) => `${(i / (xs.length - 1)) * w},${h - (y / max) * (h - 8) - 4}`).join(' ')
})
const explore = [
  { to: '/cases', t: 'Cases', d: 'Manage and track all cases' },
  { to: '/evidence', t: 'Evidence Graph', d: 'Explore evidence relationships' },
  { to: '/weave', t: 'Weave Traces', d: 'Inspect agent traces and model calls' },
  { to: '/research', t: 'Research Optimizer', d: 'Discover new evidence and hypotheses' },
  { to: '/reports', t: 'Reports', d: 'Generate and export analysis reports' },
  { to: '/settings', t: 'Settings', d: 'Configure models, agents, and preferences' },
]
</script>

<template>
  <div class="space-y-4">
    <section v-if="cs.status.value === 'idle'" class="vc-card p-6">
      <h1 class="text-2xl font-semibold">Put a DNA mutation on trial.</h1>
      <p class="mt-2 text-gray-600 max-w-3xl">One AI argues the change causes disease, another argues it is harmless, a cross-examiner throws out weak claims, and a jury updates the case file until nothing changes. Then a fixed genetics rulebook delivers the verdict.</p>
      <div class="mt-4 grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <button v-for="d in demoCards" :key="d.v" type="button" class="text-left rounded-xl border border-gray-200 hover:border-indigo-400 bg-gray-50 p-4 transition" @click="cs.open(d.v)">
          <div class="font-medium">{{ d.title }}</div>
          <div class="vc-mono text-xs text-gray-500 mt-0.5">{{ d.v }}</div>
          <p class="text-xs text-gray-500 mt-2">{{ d.blurb }}</p>
          <div class="text-xs text-indigo-600 mt-2">Open case &rarr;</div>
        </button>
      </div>
    </section>

    <template v-else>
      <div v-if="cs.error.value" class="vc-card border-red-200 bg-red-50 p-3 text-sm text-red-700 flex items-center gap-3">
        <span>The case could not finish: {{ cs.error.value }}</span>
        <UButton v-if="cs.evidence.value?.variant?.input || route.query.variant" size="xs" color="error" variant="outline" class="ml-auto" @click="cs.open(cs.evidence.value?.variant?.input ?? String(route.query.variant))">Retry</UButton>
      </div>
      <CaseHeader :cs="cs" />

      <div class="grid xl:grid-cols-[1fr_330px] gap-4">
        <section class="vc-card p-4">
          <header class="flex items-center gap-2 mb-3">
            <span class="text-indigo-600 text-lg">&#9878;</span>
            <h2 class="font-semibold">AI Courtroom</h2>
            <span class="text-sm text-gray-500">Multiple AI agents analyze evidence from different perspectives</span>
            <span v-if="isRunning && cs.activeStep.value" class="text-xs text-blue-700 vc-pulse">{{ stepLabel[cs.activeStep.value] }}</span>
            <div class="ml-auto flex gap-1">
              <button v-for="r in cs.rounds.value" :key="r.round" class="chip border" :class="cs.selectedRound.value === r.round ? 'bg-indigo-600 text-white border-indigo-600' : 'border-gray-300 text-gray-600'" @click="cs.selectedRound.value = r.round">R{{ r.round }}</button>
            </div>
          </header>
          <div class="grid md:grid-cols-3 gap-3">
            <div class="rounded-xl bg-red-50 border border-red-100 p-4">
              <div class="flex items-center gap-2"><span class="w-9 h-9 rounded-lg bg-white text-red-600 flex items-center justify-center text-lg" :class="{ 'vc-pulse': cs.activeStep.value === 'pathogenic' }">&#9879;</span><div><div class="font-semibold text-red-700">Pathogenic Counsel</div><div class="text-xs text-gray-500">Argues for pathogenicity</div></div></div>
              <div class="mt-3 flex justify-between text-xs text-gray-600"><span>Confidence</span><b>{{ pathConf }}%</b></div>
              <div class="h-1.5 rounded bg-white mt-1"><div class="h-1.5 rounded bg-red-500 transition-all" :style="{ width: pathConf + '%' }" /></div>
              <ul class="mt-3 text-sm text-gray-700 space-y-1 list-disc ml-4 min-h-[5rem]">
                <li v-for="c in (cur?.pathogenic ?? []).slice(0, 4)" :key="c.id" :class="{ 'line-through text-gray-400': cur?.crossExam?.rejected_claim_ids.includes(c.id) }"><span v-if="c.rebuts" class="chip bg-white text-green-700 border border-green-200 mr-1">↩ rebuts benign</span>{{ c.claim }}</li>
                <li v-if="!cur?.pathogenic?.length" class="text-gray-400 list-none -ml-4">{{ isRunning ? 'Preparing arguments…' : 'No evidence-supported pathogenic claims.' }}</li>
              </ul>
              <div class="mt-3 pt-2 border-t border-red-100 text-xs text-gray-500">Key evidence</div>
              <div class="mt-1 flex flex-wrap gap-1"><span v-for="k in chips(cur?.pathogenic ?? [])" :key="k" class="chip bg-white text-red-700 border border-red-200 vc-mono">{{ k }}</span></div>
            </div>
            <div class="rounded-xl bg-blue-50 border border-blue-100 p-4">
              <div class="flex items-center gap-2"><span class="w-9 h-9 rounded-lg bg-white text-blue-600 flex items-center justify-center text-lg" :class="{ 'vc-pulse': cs.activeStep.value === 'typesafe' }">&#9673;</span><div><div class="font-semibold text-blue-700">Cross-Examiner / TypeSafe</div><div class="text-xs text-gray-500">Challenges assumptions and checks rigor</div></div></div>
              <div class="mt-3 flex justify-between text-xs text-gray-600"><span>Claims challenged</span><b>{{ xConf }}%</b></div>
              <div class="h-1.5 rounded bg-white mt-1"><div class="h-1.5 rounded bg-blue-500 transition-all" :style="{ width: xConf + '%' }" /></div>
              <ul class="mt-3 text-sm text-gray-700 space-y-1 list-disc ml-4 min-h-[5rem]">
                <li v-for="b in xBullets" :key="b">{{ b }}</li>
                <li v-if="!cur?.crossExam" class="text-gray-400 list-none -ml-4">{{ isRunning ? 'Waiting for both sides…' : '' }}</li>
              </ul>
              <div class="mt-3 pt-2 border-t border-blue-100 text-xs text-gray-500">Key findings</div>
              <div class="mt-1 flex flex-wrap gap-1">
                <span v-for="k in xChips" :key="k" class="chip bg-white text-blue-700 border border-blue-200">{{ k }}</span>
                <span v-if="cur?.crossExam" class="chip bg-white text-gray-600 border border-gray-200">{{ cur.crossExam.rejected_claim_ids.length }} rejected · {{ cur.crossExam.weakened_claim_ids.length }} weakened</span>
              </div>
            </div>
            <div class="rounded-xl bg-green-50 border border-green-100 p-4">
              <div class="flex items-center gap-2"><span class="w-9 h-9 rounded-lg bg-white text-green-600 flex items-center justify-center text-lg" :class="{ 'vc-pulse': cs.activeStep.value === 'benign' }">&#10003;</span><div><div class="font-semibold text-green-700">Benign Counsel</div><div class="text-xs text-gray-500">Argues for benign interpretation</div></div></div>
              <div class="mt-3 flex justify-between text-xs text-gray-600"><span>Confidence</span><b>{{ benConf }}%</b></div>
              <div class="h-1.5 rounded bg-white mt-1"><div class="h-1.5 rounded bg-green-500 transition-all" :style="{ width: benConf + '%' }" /></div>
              <ul class="mt-3 text-sm text-gray-700 space-y-1 list-disc ml-4 min-h-[5rem]">
                <li v-for="c in (cur?.benign ?? []).slice(0, 4)" :key="c.id" :class="{ 'line-through text-gray-400': cur?.crossExam?.rejected_claim_ids.includes(c.id) }"><span v-if="c.rebuts" class="chip bg-white text-red-700 border border-red-200 mr-1">↩ rebuts pathogenic</span>{{ c.claim }}</li>
                <li v-if="!cur?.benign?.length" class="text-gray-400 list-none -ml-4">{{ isRunning && !cur?.crossExam ? 'Preparing arguments…' : 'No evidence-supported benign claims.' }}</li>
              </ul>
              <div class="mt-3 pt-2 border-t border-green-100 text-xs text-gray-500">Key evidence</div>
              <div class="mt-1 flex flex-wrap gap-1"><span v-for="k in chips(cur?.benign ?? [])" :key="k" class="chip bg-white text-green-700 border border-green-200 vc-mono">{{ k }}</span></div>
            </div>
          </div>
          <div v-if="cur?.jury" class="mt-3 rounded-lg bg-amber-50 border border-amber-100 px-3 py-2 text-sm text-amber-900"><b>Jury:</b> {{ cur.jury.rationale }}</div>
        </section>

        <section class="vc-card p-4">
          <header class="flex items-center gap-2 mb-3"><span class="text-indigo-600">&#9719;</span><h2 class="font-semibold">Deliberation Timeline</h2><NuxtLink to="/timeline" class="ml-auto text-xs text-indigo-600">View all</NuxtLink></header>
          <DeliberationTimeline :cs="cs" />
        </section>
      </div>

      <div class="grid xl:grid-cols-[1.3fr_1fr_1fr] gap-4">
        <section class="vc-card p-4">
          <header class="flex items-center mb-3"><div><h2 class="font-semibold">Evidence Graph</h2><div class="text-xs text-gray-500">From variant to evidence to ACMG criteria to conclusion</div></div><NuxtLink to="/evidence" class="ml-auto text-xs text-indigo-600">View full graph</NuxtLink></header>
          <EvidenceGraph :cs="cs" />
        </section>
        <section class="vc-card p-4">
          <header class="flex items-center mb-2"><div><h2 class="font-semibold">Weave Observability</h2><div class="text-xs text-gray-500">Live agent activity across all cases</div></div><a v-if="cs.config.value?.weave_url" :href="cs.config.value.weave_url" target="_blank" class="ml-auto text-xs text-indigo-600">Open Weave ↗</a></header>
          <svg v-if="spark" viewBox="0 0 300 70" class="w-full h-20"><polyline :points="spark" fill="none" stroke="#6366f1" stroke-width="2" /></svg>
          <div class="text-[10px] text-gray-400 mb-2">latency of the last {{ stats?.recent_latency_ms?.length ?? 0 }} cases</div>
          <div class="grid grid-cols-2 gap-2 text-sm">
            <div class="rounded-lg bg-gray-50 p-2"><div class="text-lg font-semibold">{{ stats?.events?.toLocaleString() ?? '–' }}</div><div class="text-xs text-gray-500">Traces</div></div>
            <div class="rounded-lg bg-gray-50 p-2"><div class="text-lg font-semibold">{{ stats?.agent_calls?.toLocaleString() ?? '–' }}</div><div class="text-xs text-gray-500">Agent calls</div></div>
            <div class="rounded-lg bg-gray-50 p-2"><div class="text-lg font-semibold">{{ stats ? (stats.avg_latency_ms / 1000).toFixed(1) + 's' : '–' }}</div><div class="text-xs text-gray-500">Avg latency</div></div>
            <div class="rounded-lg bg-gray-50 p-2"><div class="text-lg font-semibold">{{ stats ? Math.round(stats.converged_rate * 100) + '%' : '–' }}</div><div class="text-xs text-gray-500">Converged</div></div>
          </div>
        </section>
        <section class="vc-card p-4 flex flex-col">
          <header class="mb-3"><h2 class="font-semibold">ARIA — Research Optimizer</h2><div class="text-xs text-gray-500">Find new angles, evidence, and validation strategies</div></header>
          <div v-if="rec" class="rounded-lg bg-indigo-50 border border-indigo-100 p-3 text-sm">
            <div class="flex items-start gap-2"><b class="leading-snug">{{ rec.recommended_experiment }}</b><span class="ml-auto chip bg-green-100 text-green-700 whitespace-nowrap">{{ rec.runs_analyzed }} runs</span></div>
            <p class="text-xs text-gray-600 mt-1">{{ rec.hypothesis }}</p>
          </div>
          <ul v-if="rec" class="mt-3 text-xs text-gray-700 space-y-1 list-disc ml-4">
            <li>{{ rec.observed }}</li>
            <li>{{ rec.expected_improvement }}</li>
          </ul>
          <div class="mt-auto pt-3"><UButton color="primary" block :loading="runningPlan" @click="runPlan">Run Research Plan &rarr;</UButton></div>
        </section>
      </div>
    </template>

    <section>
      <h2 class="font-semibold mb-2">Explore Pages</h2>
      <div class="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
        <NuxtLink v-for="e in explore" :key="e.to" :to="e.to" class="vc-card p-3 hover:border-indigo-400 flex items-center gap-3">
          <span class="w-9 h-9 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">▣</span>
          <div class="min-w-0"><div class="font-medium text-sm">{{ e.t }}</div><div class="text-xs text-gray-500 truncate">{{ e.d }}</div></div>
          <span class="ml-auto text-gray-400">›</span>
        </NuxtLink>
      </div>
    </section>
  </div>
</template>
