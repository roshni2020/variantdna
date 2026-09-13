"""Shared Pydantic schemas. Every agent, the reducer, the rule engine and the API use these.

Rules enforced elsewhere but assumed here:
- Evidence is immutable once ingested.
- Agents only cite evidence IDs that exist in EvidenceState.evidence_items.
- Only the deterministic reducer mutates EvidenceState.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Direction = Literal["pathogenic", "benign", "neutral"]
Severity = Literal["low", "medium", "high"]
ClaimAction = Literal["accept", "weaken", "reject", "unchanged"]


class NormalizedVariant(BaseModel):
    input: str
    gene: str | None = None
    transcript: str | None = None
    hgvs: str | None = None
    protein_change: str | None = None  # set when the user gave a protein-level name
    rsid: str | None = None
    assembly: str | None = None


class DiseaseContext(BaseModel):
    disease_name: str | None = None
    mondo_id: str | None = None


class EvidenceItem(BaseModel):
    id: str
    source: str
    evidence_type: str
    summary: str
    direction: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    source_url: str | None = None
    source_identifier: str | None = None
    transcript: str | None = None
    metadata: dict = Field(default_factory=dict)


class AgentClaim(BaseModel):
    id: str
    agent: str
    claim: str
    evidence_ids: list[str]
    proposed_criterion: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    assumptions: list[str] = Field(default_factory=list)
    rebuts: str | None = None  # id of the opposing claim this one answers, if any


class Conflict(BaseModel):
    id: str
    conflict_type: str
    description: str
    affected_claim_ids: list[str] = Field(default_factory=list)
    severity: Severity
    resolved: bool = False


class CrossExamResult(BaseModel):
    contradictions: list[Conflict] = Field(default_factory=list)
    rejected_claim_ids: list[str] = Field(default_factory=list)
    weakened_claim_ids: list[str] = Field(default_factory=list)
    validated_claim_ids: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    recommended_checks: list[str] = Field(default_factory=list)
    provider: str = "unknown"


class CriterionState(BaseModel):
    code: str
    status: str
    strength: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class EvidenceState(BaseModel):
    variant: NormalizedVariant
    disease_context: DiseaseContext | None = None

    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    pathogenic_claims: list[AgentClaim] = Field(default_factory=list)
    benign_claims: list[AgentClaim] = Field(default_factory=list)

    # claim_id -> last jury action (accept/weaken/reject/unchanged). Lets agents avoid
    # re-proposing rejected claims without passing conversation history around.
    claim_status: dict[str, ClaimAction] = Field(default_factory=dict)

    conflicts: list[Conflict] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)

    criterion_states: dict[str, CriterionState] = Field(default_factory=dict)

    sources_loaded: list[str] = Field(default_factory=list)

    round: int = 0
    state_hash: str = ""
    confidence_score: float = 0.0
    converged: bool = False

    def evidence_ids(self) -> set[str]:
        return {e.id for e in self.evidence_items}

    def evidence_by_id(self) -> dict[str, EvidenceItem]:
        return {e.id: e for e in self.evidence_items}

    def unresolved_conflicts(self, severity: Severity | None = None) -> list[Conflict]:
        return [
            c
            for c in self.conflicts
            if not c.resolved and (severity is None or c.severity == severity)
        ]


class ClaimDecision(BaseModel):
    claim_id: str
    action: ClaimAction
    rationale: str
    new_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class JuryDelta(BaseModel):
    """Structured state delta proposed by the Jury. Applied only by the reducer."""

    claim_decisions: list[ClaimDecision] = Field(default_factory=list)
    conflicts_to_add: list[Conflict] = Field(default_factory=list)
    conflicts_to_resolve: list[str] = Field(default_factory=list)
    criterion_updates: list[CriterionState] = Field(default_factory=list)
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    request_another_round: bool = True
    rationale: str = ""


class RoundResult(BaseModel):
    round_number: int
    previous_state_hash: str
    new_state_hash: str
    changes: list[str] = Field(default_factory=list)
    conflicts_added: list[str] = Field(default_factory=list)
    conflicts_resolved: list[str] = Field(default_factory=list)
    invalid_claim_ids: list[str] = Field(default_factory=list)


class CriterionResult(BaseModel):
    code: str
    status: str
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str


class Verdict(BaseModel):
    classification: str
    criteria: list[CriterionResult] = Field(default_factory=list)
    unresolved_conflicts: list[Conflict] = Field(default_factory=list)
    rounds_used: int
    requires_human_review: bool
    converged: bool = False
    disclaimer: str = "Simplified ACMG-style research rules. Not for clinical use."


class RoundSnapshot(BaseModel):
    """Everything the UI needs to show 'what changed in round N'."""

    round_number: int
    pathogenic_claims: list[AgentClaim]
    benign_claims: list[AgentClaim]
    cross_exam: CrossExamResult
    jury_delta: JuryDelta
    round_result: RoundResult
    state_after: EvidenceState


class CaseResult(BaseModel):
    case_id: str
    state: EvidenceState
    rounds: list[RoundSnapshot] = Field(default_factory=list)
    verdict: Verdict
