/** Resolve which case a sub-page should show: ?case= query, else the last one opened, else the latest completed. */
export function useCaseRoute() {
  const cs = useCase()
  const route = useRoute()

  async function resolve() {
    let id = typeof route.query.case === 'string' ? route.query.case : null
    if (!id) { try { id = localStorage.getItem('vc:lastCase') } catch {} }
    if (!id) {
      try {
        const list = await cs.api.get<any[]>('/v1/cases?limit=20')
        id = list.find(c => c.status === 'completed')?.id ?? null
      } catch {}
    }
    if (id) await cs.load(id)
    return id
  }
  onMounted(resolve)
  return cs
}
