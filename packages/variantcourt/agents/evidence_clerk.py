"""Evidence Clerk: fetch, normalize, validate, deduplicate, store provenance.

The clerk never decides pathogenic vs benign. It only builds the initial EvidenceState.
"""

from __future__ import annotations

import logging
from typing import Protocol

from variantcourt.domain import DiseaseContext, EvidenceItem, EvidenceState, NormalizedVariant, compute_state_hash

from variantcourt.evidence.fixtures import FIXTURES, sparse_fixture
from variantcourt.evidence.normalize import normalize_variant, variant_key


log = logging.getLogger(__name__)


class EvidenceClerk(Protocol):
    name: str

    async def build_state(self, variant_input: str) -> EvidenceState: ...


def _dedupe(items: list[EvidenceItem]) -> list[EvidenceItem]:
    seen: set[tuple] = set()
    out: list[EvidenceItem] = []
    for item in items:
        key = (item.source, item.evidence_type, item.source_identifier or item.summary)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def assemble_state(
    variant: NormalizedVariant,
    items: list[EvidenceItem],
    sources: list[str],
    disease_context: DiseaseContext | None = None,
) -> EvidenceState:
    ids = [i.id for i in items]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate evidence IDs in bundle")
    state = EvidenceState(
        variant=variant,
        disease_context=disease_context,
        evidence_items=_dedupe(items),
        sources_loaded=sources,
    )
    state.state_hash = compute_state_hash(state)
    return state


class MockEvidenceClerk:
    """DEMO MODE clerk backed by deterministic fixtures."""

    name = "evidence_clerk(mock)"

    async def build_state(self, variant_input: str) -> EvidenceState:
        parsed = normalize_variant(variant_input)
        bundle = FIXTURES.get(variant_key(parsed))
        if bundle is None:
            bundle = sparse_fixture(parsed)
            variant = parsed
        else:
            variant = bundle["variant"].model_copy(update={"input": variant_input})
        return assemble_state(
            variant=variant,
            items=list(bundle["evidence"]),
            sources=list(bundle["sources"]),
            disease_context=bundle.get("disease_context"),
        )


class LiveEvidenceClerk:
    """LIVE MODE clerk: Ensembl VEP -> gnomAD -> ClinVar -> Europe PMC, cached on disk.

    Sources fail independently. If VEP (the anchor) fails and nothing is cached, the
    fixture clerk answers instead and the state says so in sources_loaded.
    """

    name = "evidence_clerk(live)"

    def __init__(self, cache=None, refresh: bool = False, fallback: MockEvidenceClerk | None = None):
        from variantcourt.evidence.cache import EvidenceCache

        self.cache = cache or EvidenceCache()
        self.refresh = refresh
        self.fallback = fallback or MockEvidenceClerk()
        self.last_errors: dict[str, str] = {}

    async def build_state(self, variant_input: str) -> EvidenceState:
        import asyncio

        parsed = normalize_variant(variant_input)
        key = variant_key(parsed)
        cached = None if self.refresh else self.cache.get(key)
        if cached is None:
            bundle = await asyncio.to_thread(self._fetch_bundle, parsed)
            if bundle is None:
                state = await self.fallback.build_state(variant_input)
                state.sources_loaded = [f"{s} (fixture fallback)" for s in state.sources_loaded]
                return state
            if "ClinVar" not in bundle.get("errors", {}):  # a bundle missing ClinVar is not worth remembering
                self.cache.put(key, bundle)
        else:
            bundle = cached
        variant = NormalizedVariant.model_validate(bundle["variant"]).model_copy(update={"input": variant_input})
        items = [EvidenceItem.model_validate(i) for i in bundle["evidence"]]
        disease = DiseaseContext.model_validate(bundle["disease_context"]) if bundle.get("disease_context") else None
        sources = list(bundle["sources"]) + (["cache"] if cached is not None else [])
        return assemble_state(variant=variant, items=items, sources=sources, disease_context=disease)

    def _fetch_bundle(self, parsed: NormalizedVariant) -> dict | None:
        from variantcourt.evidence import sources as src

        self.last_errors = {}
        try:
            rec = src.fetch_vep(parsed)
        except Exception as e:  # noqa: BLE001
            self.last_errors["Ensembl VEP"] = str(e)
            log.warning("VEP failed for %s: %s", parsed.input, e)
            return None
        items, variant = src.vep_items(rec, parsed)
        loaded = ["Ensembl VEP"]
        cons = next((i for i in items if i.id == "ev_vep_consequence"), None)
        hgvsc = cons.metadata.get("hgvsc") if cons else None
        protein = cons.metadata.get("protein_change") if cons else None

        pop_items: list[EvidenceItem] = []
        if variant.rsid:
            try:
                pop_items = src.fetch_gnomad(variant.rsid, variant.transcript)
                if pop_items:
                    loaded.append("gnomAD")
            except Exception as e:  # noqa: BLE001
                self.last_errors["gnomAD"] = str(e)
                log.warning("gnomAD failed: %s", e)
        if not pop_items:
            fallback = src.vep_population_item(rec, variant.transcript)
            if fallback:
                pop_items = [fallback]
                loaded.append("gnomAD (via VEP)")
        items.extend(pop_items)

        try:
            cv = src.fetch_clinvar(variant, hgvsc)
            if cv:
                loaded.append("ClinVar")
            items.extend(cv)
        except Exception as e:  # noqa: BLE001
            self.last_errors["ClinVar"] = str(e)
            log.warning("ClinVar failed: %s", e)

        try:
            lit = src.fetch_europepmc(variant, protein, hgvsc)
            if lit:
                loaded.append("Europe PMC")
            items.extend(lit)
        except Exception as e:  # noqa: BLE001
            self.last_errors["Europe PMC"] = str(e)
            log.warning("Europe PMC failed: %s", e)

        conditions = [c for i in items if i.source == "ClinVar" for c in i.metadata.get("conditions", [])]
        disease = DiseaseContext(disease_name=conditions[0]) if conditions else None
        return {
            "variant": variant.model_dump(),
            "disease_context": disease.model_dump() if disease else None,
            "sources": loaded,
            "evidence": [i.model_dump() for i in items],
            "errors": self.last_errors,
        }
