<script setup lang="ts">
const q = ref('')
const router = useRouter()
const route = useRoute()
function run() {
  if (q.value.trim()) router.push({ path: '/', query: { variant: q.value.trim(), t: Date.now() } })
}
const nav = [
  { to: '/', label: 'Dashboard', icon: '▦' },
  { to: '/lookup', label: 'Variant Lookup', icon: '⌕' },
  { to: '/cases', label: 'Cases', icon: '▤' },
  { to: '/evidence', label: 'Evidence Graph', icon: '⋔' },
  { to: '/timeline', label: 'Timeline', icon: '∿' },
  { to: '/weave', label: 'Weave Traces', icon: '≋' },
  { to: '/research', label: 'Research Optimizer', icon: '✦' },
  { to: '/sources', label: 'Sources', icon: '▣' },
  { to: '/reports', label: 'Reports', icon: '▧' },
  { to: '/settings', label: 'Settings', icon: '⚙' },
]
const crumb = computed(() => nav.find(n => n.to === route.path)?.label ?? 'Dashboard')
</script>

<template>
  <UApp>
    <div class="min-h-screen flex">
      <aside class="w-56 shrink-0 border-r border-gray-200 bg-white px-3 py-4 hidden md:flex flex-col">
        <NuxtLink to="/" class="flex items-center gap-2 px-2 mb-5">
          <span class="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center font-bold">V</span>
          <span class="text-lg font-semibold">VariantCourt</span>
        </NuxtLink>
        <nav class="vc-nav flex flex-col gap-0.5">
          <NuxtLink v-for="n in nav" :key="n.to" :to="n.to" :class="{ 'router-link-active': route.path === n.to }"><span class="w-5 text-center text-gray-400">{{ n.icon }}</span>{{ n.label }}</NuxtLink>
        </nav>
        <div class="mt-auto text-xs text-gray-500 rounded-lg bg-gray-50 p-3">
          AI agents for genetic variant interpretation.
          <div class="mt-1">More evidence. Clearer answers.</div>
          <div class="mt-2 text-amber-700">Research prototype. Not for clinical diagnosis.</div>
        </div>
      </aside>
      <div class="flex-1 min-w-0">
        <header class="bg-white border-b border-gray-200 px-4 py-2.5 flex items-center gap-3">
          <form class="flex-1 max-w-2xl flex items-center gap-2 bg-gray-50 border border-gray-200 rounded-lg px-3" @submit.prevent="run">
            <span class="text-gray-400">&#9906;</span>
            <input v-model="q" class="vc-mono flex-1 bg-transparent py-2 text-sm outline-none" placeholder="Search for a variant, gene, or disease..." />
            <span class="hidden lg:inline text-xs text-gray-400">e.g. NM_007294.4:c.68_69delAG, rs80357914</span>
          </form>
          <NuxtLink to="/" class="text-sm border border-gray-200 rounded-lg px-3 py-2 hover:bg-gray-50">+ New Case</NuxtLink>
          <UButton color="primary" @click="run">▶ Run Analysis</UButton>
          <div class="hidden sm:flex items-center gap-2 pl-2 border-l border-gray-200">
            <span class="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-sm font-semibold">R</span>
            <div class="leading-tight"><div class="text-sm font-medium">Roshni</div><div class="text-xs text-gray-500">Researcher</div></div>
          </div>
        </header>
        <main class="p-4 max-w-[1500px]">
          <div class="text-sm text-gray-500 mb-3"><NuxtLink to="/" class="hover:underline">Dashboard</NuxtLink><span v-if="crumb !== 'Dashboard'"> &rsaquo; {{ crumb }}</span></div>
          <NuxtPage />
        </main>
      </div>
    </div>
  </UApp>
</template>
