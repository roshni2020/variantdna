import type { EvidenceState, RoundView, Verdict } from './useApi'

interface LogEntry { t: number; who: string; text: string; tone: 'path' | 'benign' | 'typesafe' | 'jury' | 'system' }

export function useCase() {
  const api = useApi()
  const caseId = ref<string | null>(null)
  const status = ref<'idle' | 'running' | 'completed' | 'failed'>('idle')
  const error = ref<string | null>(null)
  const evidence = ref<EvidenceState | null>(null)
  const rounds = ref<RoundView[]>([])
  const verdict = ref<Verdict | null>(null)
  const selectedRound = ref<number | null>(null)
  const activeStep = ref<string | null>(null)
  const log = ref<LogEntry[]>([])
  const config = ref<{ max_rounds: number; mode: string; wandb_url?: string | null; weave_url?: string | null } | null>(null)
  const wandbUrl = ref<string | null>(null)
  let es: EventSource | null = null

  function reset() {
    es?.close()
    es = null
    status.value = 'idle'
    error.value = null
    evidence.value = null
    rounds.value = []
    verdict.value = null
    selectedRound.value = null
    activeStep.value = null
    log.value = []
    wandbUrl.value = null
  }

  function roundAt(n: number): RoundView {
    let r = rounds.value.find(x => x.round === n)
    if (!r) {
      r = { round: n, pathogenic: [], benign: [], crossExam: null, jury: null, result: null, stateAfter: null, metrics: null, sources: {} }
      rounds.value.push(r)
    }
    return r
  }

  function say(who: string, text: string, tone: LogEntry['tone']) {
    log.value.push({ t: Date.now(), who, text, tone })
  }

  function handle(name: string, payload: any) {
    switch (name) {
      case 'case_created':
        say('Clerk', `Case opened for ${payload.variant} (${payload.mode} mode)`, 'system')
        break
      case 'evidence_retrieved':
        evidence.value = payload.state
        say('Evidence Clerk', `${payload.evidence_count} evidence items from ${payload.sources.join(', ')}`, 'system')
        break
      case 'round_started':
        activeStep.value = 'pathogenic'
        selectedRound.value = payload.round
        roundAt(payload.round)
        say('Court', `Round ${payload.round} of ${payload.max_rounds} begins`, 'system')
        break
      case 'pathogenic_agent': {
        const r = roundAt(payload.round)
        r.pathogenic = payload.claims
        r.sources.pathogenic = payload.source
        activeStep.value = 'benign'
        say('Pathogenic Counsel', `${payload.claims.length} claims: ${payload.claims.map((c: any) => c.proposed_criterion || 'context').join(', ')}`, 'path')
        break
      }
      case 'benign_agent': {
        const r = roundAt(payload.round)
        r.benign = payload.claims
        r.sources.benign = payload.source
        activeStep.value = 'typesafe'
        say('Benign Counsel', payload.claims.length ? `${payload.claims.length} claims: ${payload.claims.map((c: any) => c.proposed_criterion || 'context').join(', ')}` : 'No evidence-supported benign claims this round', 'benign')
        break
      }
      case 'typesafe_cross_exam': {
        const r = roundAt(payload.round)
        r.crossExam = payload.result
        activeStep.value = 'jury'
        const x = payload.result
        say('TypeSafe', `${x.validated_claim_ids.length} validated, ${x.weakened_claim_ids.length} weakened, ${x.rejected_claim_ids.length} rejected, ${x.contradictions.length} findings`, 'typesafe')
        break
      }
      case 'jury': {
        const r = roundAt(payload.round)
        r.jury = payload.delta
        r.sources.jury = payload.source
        activeStep.value = 'reducer'
        say('Jury', payload.delta.rationale, 'jury')
        break
      }
      case 'round_completed': {
        const r = roundAt(payload.round)
        r.result = payload.round_result
        r.stateAfter = payload.state
        r.metrics = payload.metrics
        activeStep.value = null
        say('Court', payload.converged ? `Round ${payload.round}: no material change. Converged.` : `Round ${payload.round}: ${payload.round_result.changes.length} state changes`, 'system')
        break
      }
      case 'verdict':
        verdict.value = payload.verdict
        say('Rule engine', `Deterministic classification: ${payload.classification}`, 'system')
        break
      case 'case_completed':
        status.value = 'completed'
        wandbUrl.value = payload.wandb_url ?? null
        if (payload.wandb_url) say('W&B', 'Run logged for ARIA', 'system')
        es?.close()
        break
      case 'case_failed':
        status.value = 'failed'
        error.value = payload.error
        es?.close()
        break
    }
  }

  async function open(variant: string, maxRounds?: number) {
    reset()
    status.value = 'running'
    try {
      const created = await api.post<{ id: string }>('/v1/cases', { variant, max_rounds: maxRounds ?? null })
      caseId.value = created.id
      try { localStorage.setItem('vc:lastCase', created.id) } catch {}
      attach(created.id)
    } catch (e: any) {
      status.value = 'failed'
      error.value = e.message
    }
  }

  function attach(id: string) {
    es?.close()
    es = api.stream(id)
    const names = ['case_created', 'evidence_retrieved', 'round_started', 'pathogenic_agent', 'benign_agent', 'typesafe_cross_exam', 'jury', 'round_completed', 'verdict', 'case_completed', 'case_failed']
    for (const n of names) {
      es.addEventListener(n, (ev: MessageEvent) => {
        const msg = JSON.parse(ev.data)
        handle(msg.name, msg.payload)
      })
    }
    es.onerror = () => {
      if (status.value === 'running') {
        // fall back to polling the stored result
        setTimeout(async () => {
          try {
            const c = await api.get<any>(`/v1/cases/${id}`)
            if (c.status === 'completed') loadResult(c)
            else if (c.status === 'failed') { status.value = 'failed'; error.value = c.error; es?.close() }
          } catch {}
        }, 1000)
      }
    }
  }

  function loadResult(c: any) {
    reset()
    caseId.value = c.id
    try { localStorage.setItem('vc:lastCase', c.id) } catch {}
    const res = c.result
    evidence.value = res.state
    rounds.value = res.rounds.map((s: any) => ({
      round: s.round_number,
      pathogenic: s.pathogenic_claims,
      benign: s.benign_claims,
      crossExam: s.cross_exam,
      jury: s.jury_delta,
      result: s.round_result,
      stateAfter: s.state_after,
      metrics: null,
      sources: {},
    }))
    verdict.value = res.verdict
    selectedRound.value = rounds.value.length
    status.value = 'completed'
  }

  async function load(id: string) {
    const c = await api.get<any>(`/v1/cases/${id}`)
    if (c.status === 'completed') loadResult(c)
    else if (c.status === 'failed') { reset(); caseId.value = id; status.value = 'failed'; error.value = c.error }
    else {
      reset()
      caseId.value = id
      try { localStorage.setItem('vc:lastCase', id) } catch {}
      status.value = 'running'
      attach(id)
    }
  }

  onBeforeUnmount(() => es?.close())

  const current = computed(() => {
    const n = selectedRound.value ?? rounds.value.length
    return rounds.value.find(r => r.round === n) ?? null
  })

  return { api, caseId, status, error, evidence, rounds, verdict, selectedRound, current, activeStep, log, config, wandbUrl, open, load }
}
