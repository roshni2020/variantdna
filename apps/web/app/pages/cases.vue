<script setup lang="ts">
const api = useApi()
const cases = ref<any[]>([])
onMounted(async () => { try { cases.value = await api.get('/v1/cases?limit=100') } catch {} })
</script>

<template>
  <section class="vc-card p-4">
    <h1 class="font-semibold mb-3">Cases</h1>
    <table class="w-full text-sm">
      <thead class="text-xs text-gray-500 text-left"><tr><th>Case</th><th>Variant</th><th>Status</th><th>Rounds</th><th>TypeSafe</th><th>Created</th></tr></thead>
      <tbody>
        <tr v-for="c in cases" :key="c.id" class="border-t border-gray-100">
          <td class="vc-mono"><NuxtLink :to="{ path: '/', query: { case: c.id } }" class="text-indigo-600 underline">{{ c.id }}</NuxtLink></td>
          <td class="vc-mono">{{ c.variant }}</td>
          <td><span class="chip" :class="c.status === 'completed' ? 'bg-green-100 text-green-700' : c.status === 'failed' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'">{{ c.status }}</span></td>
          <td>{{ c.config.max_rounds }}</td>
          <td>{{ c.config.typesafe_enabled === false ? 'off' : 'on' }}</td>
          <td class="text-gray-500">{{ new Date(c.created_at * 1000).toLocaleString() }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>
