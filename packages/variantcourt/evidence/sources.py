"""Live evidence sources: Ensembl VEP, gnomAD, ClinVar, Europe PMC.

Each fetcher is independent and returns a list of EvidenceItem. Failures are logged and
return [] so the courtroom still runs on whatever came back. Nothing here decides
pathogenic vs benign; direction is a literal reading of what the source asserts.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from variantcourt.domain import EvidenceItem, NormalizedVariant

log = logging.getLogger(__name__)

TIMEOUT = 25.0
UA = {"User-Agent": "VariantCourt/0.2 (research prototype)"}
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Genes where loss of function is an established disease mechanism (ClinGen dosage
# haploinsufficiency = 3, curated subset). Research shortcut, not a clinical resource.
LOF_MECHANISM_GENES = {
    "BRCA1", "BRCA2", "TP53", "MLH1", "MSH2", "MSH6", "PMS2", "APC", "PTEN", "RB1", "NF1",
    "NF2", "CDH1", "PALB2", "ATM", "CHEK2", "STK11", "VHL", "TSC1", "TSC2", "DMD", "CFTR",
    "SMAD4", "BMPR1A", "MEN1", "RET", "SDHB", "SDHD", "FBN1", "COL3A1", "LDLR", "MYBPC3",
    "PKD1", "PKD2", "SCN1A", "MECP2", "KMT2D", "ARID1B", "PTPN11",
}
LOF_CONSEQUENCES = {"frameshift_variant", "stop_gained", "splice_acceptor_variant", "splice_donor_variant", "start_lost"}


# ---------------------------------------------------------------- name resolution
_CLINVAR_TITLE = re.compile(r"^(N[MR]_\d+\.\d+)\(([A-Za-z0-9\-]+)\):(c\.[^ ]+)")


def resolve_protein_name(gene: str, protein_change: str) -> tuple[str, str] | None:
    """'BRAF' + 'p.Val600Glu' -> ('NM_004333.6', 'c.1799T>A') using ClinVar's own naming.

    ponytail: reuses the ClinVar E-utilities we already call; Ensembl's variant_recoder
    does the same job but times out regularly on the public endpoint.
    """
    term = f'{gene}[gene] AND "{protein_change}"[variant name]'
    r = httpx.get(
        f"{EUTILS}/esearch.fcgi",
        params={"db": "clinvar", "term": term, "retmode": "json", "retmax": 5},
        headers=UA,
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    ids = (r.json().get("esearchresult") or {}).get("idlist", [])
    if not ids:
        return None
    r = httpx.get(
        f"{EUTILS}/esummary.fcgi",
        params={"db": "clinvar", "id": ",".join(ids), "retmode": "json"},
        headers=UA,
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    result = r.json().get("result", {})
    for uid in result.get("uids", []):
        m = _CLINVAR_TITLE.match(result[uid].get("title", ""))
        if m and m.group(2).upper() == gene.upper():
            return m.group(1), m.group(3)
    return None


# ---------------------------------------------------------------- Ensembl VEP
def fetch_vep(variant: NormalizedVariant) -> dict[str, Any]:
    """Raw VEP record for the variant (transcript HGVS or rsID). Raises on failure."""
    if variant.transcript and variant.hgvs:
        term = f"{variant.transcript}:{variant.hgvs}"
    elif variant.rsid:
        term = variant.rsid
    elif variant.gene and variant.hgvs:
        term = f"{variant.gene}:{variant.hgvs}"
    else:
        raise ValueError("variant lacks transcript/rsid for VEP")
    path = "id" if term.startswith("rs") else "hgvs"
    r = httpx.get(
        f"https://rest.ensembl.org/vep/human/{path}/{term}",
        params={"content-type": "application/json", "refseq": 1, "hgvs": 1, "sift": "b", "polyphen": "b"},
        headers={**UA, "Accept": "application/json"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    if not data:
        raise ValueError("VEP returned no records")
    return data[0]


def _pick_transcript(rec: dict[str, Any], transcript: str | None) -> dict[str, Any] | None:
    tcs = rec.get("transcript_consequences") or []
    if transcript:
        base = transcript.split(".")[0]
        for tc in tcs:
            if tc.get("transcript_id", "").split(".")[0] == base:
                return tc
    nm = [tc for tc in tcs if tc.get("transcript_id", "").startswith("NM_")]
    return (next((tc for tc in nm if tc.get("mane_select") or tc.get("mane")), None)
            or next((tc for tc in nm if tc.get("canonical")), None)
            or next((tc for tc in tcs if tc.get("canonical")), None) or (nm or tcs or [None])[0])


def vep_items(rec: dict[str, Any], variant: NormalizedVariant) -> tuple[list[EvidenceItem], NormalizedVariant]:
    """Consequence + in-silico items, plus an enriched NormalizedVariant (gene, rsid)."""
    items: list[EvidenceItem] = []
    tc = _pick_transcript(rec, variant.transcript)
    gene = (tc or {}).get("gene_symbol") or variant.gene
    picked = (tc or {}).get("transcript_id")
    # The case transcript is what the user asked for. If VEP only annotated another transcript,
    # the consequence item carries that transcript, so the rule engine ignores it and the
    # cross-examiner flags any claim built on it, instead of the swap going unnoticed.
    tx_id = variant.transcript or picked
    rsid = variant.rsid
    for cv in rec.get("colocated_variants") or []:
        if str(cv.get("id", "")).startswith("rs"):
            rsid = cv["id"]
            break
    hgvs = variant.hgvs or ((tc or {}).get("hgvsc") or "").split(":")[-1] or None
    enriched = variant.model_copy(update={"gene": gene, "transcript": tx_id, "rsid": rsid, "hgvs": hgvs})
    if tc is None:
        return items, enriched

    consequence = (tc.get("consequence_terms") or [rec.get("most_severe_consequence", "unknown")])[0]
    lof = consequence in LOF_CONSEQUENCES
    direction = "pathogenic" if lof and gene in LOF_MECHANISM_GENES else "neutral"
    protein = (tc.get("hgvsp") or "").split(":")[-1]
    items.append(
        EvidenceItem(
            id="ev_vep_consequence",
            source="Ensembl VEP",
            evidence_type="consequence",
            summary=(
                f"{consequence.replace('_', ' ')} in {gene} ({tx_id}"
                + (f", {protein}" if protein else "")
                + f"); VEP impact {tc.get('impact', '?')}."
                + (" Loss of function is an established mechanism for this gene (curated list)." if lof and gene in LOF_MECHANISM_GENES else "")
            ),
            direction=direction,
            confidence=0.85 if lof else 0.5,
            source_url=f"https://rest.ensembl.org/vep/human/hgvs/{tx_id}:{variant.hgvs}" if variant.hgvs else None,
            source_identifier=tc.get("hgvsc"),
            transcript=picked or tx_id,
            metadata={
                "consequence": consequence,
                "requested_transcript_annotated": (picked or "").split(".")[0] == (tx_id or "").split(".")[0],
                "impact": tc.get("impact"),
                "protein_change": protein or None,
                "hgvsc": tc.get("hgvsc"),
                "lof_mechanism": bool(lof and gene in LOF_MECHANISM_GENES),
                "canonical": bool(tc.get("canonical")),
                "assembly": rec.get("assembly_name"),
                "chrom": rec.get("seq_region_name"),
                "start": rec.get("start"),
                "end": rec.get("end"),
                "allele_string": rec.get("allele_string"),
            },
        )
    )
    # Other-transcript annotations are real evidence too; TypeSafe should catch misuse.
    for other in rec.get("transcript_consequences") or []:
        oid = other.get("transcript_id", "")
        if other is tc or not oid.startswith("NM_") or oid.split(".")[0] in {(tx_id or "").split(".")[0], (picked or "").split(".")[0]}:
            continue
        oc = (other.get("consequence_terms") or ["unknown"])[0]
        items.append(
            EvidenceItem(
                id=f"ev_vep_{oid.split('.')[0].lower()}",
                source="Ensembl VEP",
                evidence_type="consequence",
                summary=f"{oc.replace('_', ' ')} annotation on alternate transcript {oid}.",
                direction="pathogenic" if oc in LOF_CONSEQUENCES and gene in LOF_MECHANISM_GENES else "neutral",
                confidence=0.6,
                transcript=oid,
                metadata={"consequence": oc, "lof_mechanism": bool(oc in LOF_CONSEQUENCES and gene in LOF_MECHANISM_GENES), "canonical": False},
            )
        )
        break  # one alternate is enough for the record

    sift, poly = tc.get("sift_prediction"), tc.get("polyphen_prediction")
    tx_id = picked or tx_id  # in-silico scores belong to the annotated transcript
    if sift or poly:
        benign_votes = sum(1 for p in (sift, poly) if p and ("tolerated" in p or "benign" in p))
        damaging_votes = sum(1 for p in (sift, poly) if p and ("deleterious" in p or "damaging" in p))
        direction = "benign" if benign_votes and not damaging_votes else "pathogenic" if damaging_votes and not benign_votes else "neutral"
        items.append(
            EvidenceItem(
                id="ev_vep_insilico",
                source="Ensembl VEP",
                evidence_type="in_silico",
                summary=f"SIFT {sift or 'n/a'} ({tc.get('sift_score', '?')}), PolyPhen {poly or 'n/a'} ({tc.get('polyphen_score', '?')}).",
                direction=direction,
                confidence=0.55,
                transcript=tx_id,
                metadata={"sift": sift, "sift_score": tc.get("sift_score"), "polyphen": poly, "polyphen_score": tc.get("polyphen_score")},
            )
        )
    return items, enriched


def vep_population_item(rec: dict[str, Any], transcript: str | None) -> EvidenceItem | None:
    """gnomAD frequencies embedded in VEP colocated_variants; used if gnomAD API fails."""
    alt = (rec.get("allele_string") or "/").split("/")[-1]
    for cv in rec.get("colocated_variants") or []:
        freqs = cv.get("frequencies") or {}
        if alt not in freqs:
            continue  # frequencies for a different allele at this position are not this variant's
        for allele, f in ((alt, freqs[alt]),):
            af = f.get("gnomade") if f.get("gnomade") is not None else f.get("gnomadg")
            if af is None:
                continue
            popmax = max((v for k, v in f.items() if k.startswith("gnomad") and isinstance(v, (int, float))), default=af)
            return EvidenceItem(
                id="ev_gnomad_freq",
                source="gnomAD (via VEP)",
                evidence_type="population_frequency",
                summary=f"gnomAD allele frequency {af:.3g} (exomes; highest population {popmax:.3g}).",
                direction=_freq_direction(af),
                confidence=0.8,
                source_identifier=cv.get("id"),
                transcript=transcript,
                metadata={"allele_frequency": af, "popmax_af": popmax, "allele": allele, "dataset": "gnomAD via Ensembl"},
            )
    return None


def _freq_direction(af: float) -> str:
    if af > 0.01:
        return "benign"
    if af < 1e-4:
        return "pathogenic"
    return "neutral"


# ---------------------------------------------------------------- gnomAD
GNOMAD_QUERY = """
query($rsid: String!, $dataset: DatasetId!) {
  variant(rsid: $rsid, dataset: $dataset) {
    variant_id rsids
    exome { ac an af homozygote_count populations { id ac an } }
    genome { ac an af homozygote_count populations { id ac an } }
  }
}
"""


def fetch_gnomad(rsid: str, transcript: str | None) -> list[EvidenceItem]:
    r = httpx.post(
        "https://gnomad.broadinstitute.org/api",
        json={"query": GNOMAD_QUERY, "variables": {"rsid": rsid, "dataset": "gnomad_r4"}},
        headers={**UA, "Content-Type": "application/json"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    v = (r.json().get("data") or {}).get("variant")
    if not v:
        return []
    ex, ge = v.get("exome") or {}, v.get("genome") or {}
    ac = (ex.get("ac") or 0) + (ge.get("ac") or 0)
    an = (ex.get("an") or 0) + (ge.get("an") or 0)
    if not an:
        return []
    af = ac / an
    hom = (ex.get("homozygote_count") or 0) + (ge.get("homozygote_count") or 0)
    pops: dict[str, float] = {}
    for src in (ex, ge):
        for p in src.get("populations") or []:
            if p.get("an"):
                pops[p["id"]] = max(pops.get(p["id"], 0.0), p["ac"] / p["an"])
    popmax = max(pops.values()) if pops else af
    items = [
        EvidenceItem(
            id="ev_gnomad_freq",
            source="gnomAD",
            evidence_type="population_frequency",
            summary=f"gnomAD v4 allele frequency {af:.3g} ({ac} / {an} alleles, {hom} homozygotes); highest population {popmax:.3g}.",
            direction=_freq_direction(af),
            confidence=0.85,
            source_url=f"https://gnomad.broadinstitute.org/variant/{v['variant_id']}?dataset=gnomad_r4",
            source_identifier=v["variant_id"],
            transcript=transcript,
            metadata={"allele_frequency": af, "allele_count": ac, "allele_number": an, "homozygotes": hom, "popmax_af": popmax, "populations": pops, "dataset": "gnomad_r4"},
        )
    ]
    if 0 < ac and af < 1e-3:
        items.append(
            EvidenceItem(
                id="ev_gnomad_carriers",
                source="gnomAD",
                evidence_type="population_observation",
                summary=f"{ac} carrier allele(s) observed in gnomAD; carrier phenotypes are not available.",
                direction="neutral",
                confidence=0.4,
                transcript=transcript,
                metadata={"observed_in_controls": True, "allele_count": ac, "allele_frequency": af},
            )
        )
    return items


# ---------------------------------------------------------------- ClinVar
_STARS = {
    "practice guideline": 4,
    "reviewed by expert panel": 3,
    "criteria provided, multiple submitters, no conflicts": 2,
    "criteria provided, conflicting classifications": 1,
    "criteria provided, single submitter": 1,
    "no assertion criteria provided": 0,
    "no classification provided": 0,
}


def _clinvar_direction(desc: str) -> str:
    d = desc.lower()
    if "conflicting" in d:
        return "neutral"
    if "pathogenic" in d:
        return "pathogenic"
    if "benign" in d:
        return "benign"
    return "neutral"


def fetch_clinvar(variant: NormalizedVariant, hgvsc: str | None) -> list[EvidenceItem]:
    terms = []
    if variant.rsid:
        terms.append(variant.rsid)
    if hgvsc:
        terms.append(hgvsc.split(":")[-1])
    elif variant.hgvs:
        terms.append(variant.hgvs)
    term = " OR ".join(f'"{t}"' for t in terms) if terms else variant.input
    if variant.gene:
        term = f"({term}) AND {variant.gene}[gene]"
    r = httpx.get(f"{EUTILS}/esearch.fcgi", params={"db": "clinvar", "term": term, "retmode": "json", "retmax": 20}, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    ids = r.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    r = httpx.get(f"{EUTILS}/esummary.fcgi", params={"db": "clinvar", "id": ",".join(ids), "retmode": "json"}, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    result = r.json().get("result", {})
    want = (hgvsc or f"{variant.transcript}:{variant.hgvs}" or "").split(":")[-1]
    tx_base = (variant.transcript or "").split(".")[0]
    items: list[EvidenceItem] = []
    for uid in result.get("uids", []):
        rec = result[uid]
        title = rec.get("title", "")
        if want and want not in title:
            continue
        if tx_base and tx_base not in title:
            continue
        cls = rec.get("germline_classification") or rec.get("clinical_significance") or {}
        desc = cls.get("description", "not provided")
        review = cls.get("review_status", "")
        stars = _STARS.get(review, 0)
        traits = sorted({t.get("trait_name") for ts in rec.get("trait_set", []) for t in [ts] if t.get("trait_name")})[:3]
        year = (cls.get("last_evaluated") or "")[:4]
        items.append(
            EvidenceItem(
                id=f"ev_clinvar_{uid}",
                source="ClinVar",
                evidence_type="prior_classification",
                summary=f"ClinVar {rec.get('accession', uid)}: {desc} ({review or 'review status unknown'}, {stars} star{'s' if stars != 1 else ''})"
                + (f" for {', '.join(traits)}" if traits else "") + (f"; last evaluated {year}" if year else "") + ".",
                direction=_clinvar_direction(desc),
                confidence={4: 0.97, 3: 0.95, 2: 0.8, 1: 0.6, 0: 0.3}[stars],
                source_url=f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{uid}/",
                source_identifier=rec.get("accession"),
                transcript=variant.transcript,
                metadata={
                    "classification": desc,
                    "review_status": review,
                    "stars": stars,
                    "submission_year": int(year) if year.isdigit() else None,
                    "stale": bool(year.isdigit() and int(year) < 2015),
                    "conditions": traits,
                    "title": title,
                },
            )
        )
        if len(items) >= 3:
            break
    return items


# ---------------------------------------------------------------- Europe PMC
def fetch_europepmc(variant: NormalizedVariant, protein_change: str | None, hgvsc: str | None) -> list[EvidenceItem]:
    if not variant.gene:
        return []
    alts = [a for a in {hgvsc.split(":")[-1] if hgvsc else None, variant.hgvs, protein_change, variant.rsid} if a]
    if not alts:
        return []
    q = f'"{variant.gene}" AND (' + " OR ".join(f'"{a}"' for a in alts) + ")"
    r = httpx.get(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        params={"query": q, "format": "json", "pageSize": 3, "sort": "CITED desc"},
        headers=UA,
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    hits = r.json().get("resultList", {}).get("result", [])
    items = []
    for h in hits:
        pmid = h.get("pmid") or h.get("id")
        items.append(
            EvidenceItem(
                id=f"ev_pmc_{pmid}",
                source="Europe PMC",
                evidence_type="literature",
                summary=f"{h.get('title', '').rstrip('.')} ({h.get('journalTitle', 'journal')}, {h.get('pubYear', '?')}; cited {h.get('citedByCount', 0)} times).",
                direction="neutral",
                confidence=0.4,
                source_url=f"https://europepmc.org/abstract/MED/{pmid}",
                source_identifier=f"PMID:{pmid}",
                metadata={"year": h.get("pubYear"), "cited_by": h.get("citedByCount"), "note": "Literature mention only; no claim extracted."},
            )
        )
    return items
