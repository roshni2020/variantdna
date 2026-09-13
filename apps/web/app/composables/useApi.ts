export interface Claim {
  id: string
  agent: string
  claim: string
  evidence_ids: string[]
  proposed_criterion: string | null
  confidence: number
  assumptions: string[]
  rebuts?: string | null
}
export interface Conflict {
  id: string
  conflict_type: string
  description: string
  affected_claim_ids: string[]
  severity: 'low' | 'medium' | 'high'
  resolved: boolean
}
export interface CrossExam {
  contradictions: Conflict[]
  rejected_claim_ids: string[]
  weakened_claim_ids: string[]
  validated_claim_ids: string[]
  open_questions: string[]
  recommended_checks: string[]
  provider: string
}
export interface EvidenceItem {
  id: string
  source: string
  evidence_type: string
  summary: string
  direction: 'pathogenic' | 'benign' | 'neutral'
  confidence: number
  transcript: string | null
  source_identifier: string | null
  source_url: string | null
  metadata: Record<string, unknown>
}
export interface CriterionState { code: string; status: string; strength: string | null; evidence_ids: string[]; confidence: number }
export interface EvidenceState {
  variant: { input: string; gene: string | null; transcript: string | null; hgvs: string | null; rsid: string | null }
  disease_context: { disease_name: string | null } | null
  evidence_items: EvidenceItem[]
  pathogenic_claims: Claim[]
  benign_claims: Claim[]
  claim_status: Record<string, string>
  conflicts: Conflict[]
  open_questions: string[]
  criterion_states: Record<string, CriterionState>
  sources_loaded: string[]
  round: number
  state_hash: string
  confidence_score: number
  converged: boolean
}
export interface RoundResult { round_number: number; previous_state_hash: string; new_state_hash: string; changes: string[]; conflicts_added: string[]; conflicts_resolved: string[] }
export interface JuryDelta { claim_decisions: { claim_id: string; action: string; rationale: string; new_confidence: number | null }[]; rationale: string; confidence_score: number | null }
export interface Verdict {
  classification: string
  criteria: { code: string; status: string; evidence_ids: string[]; rationale: string }[]
  unresolved_conflicts: Conflict[]
  rounds_used: number
  requires_human_review: boolean
  converged: boolean
  disclaimer: string
}
export interface RoundView {
  round: number
  pathogenic: Claim[]
  benign: Claim[]
  crossExam: CrossExam | null
  jury: JuryDelta | null
  result: RoundResult | null
  stateAfter: EvidenceState | null
  metrics: Record<string, number | boolean> | null
  sources: { pathogenic?: string; benign?: string; jury?: string }
}

export function useApi() {
  const config = useRuntimeConfig()
  const base = config.public.apiBase as string

  async function get<T>(path: string): Promise<T> {
    const r = await fetch(`${base}${path}`)
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
    return r.json()
  }
  async function post<T>(path: string, body: unknown): Promise<T> {
    const r = await fetch(`${base}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
    return r.json()
  }
  function stream(caseId: string): EventSource {
    return new EventSource(`${base}/v1/cases/${caseId}/stream`)
  }
  return { base, get, post, stream }
}
