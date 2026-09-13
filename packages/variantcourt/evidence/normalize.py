"""Variant input normalization. Small and forgiving; the Evidence Clerk refines it."""

from __future__ import annotations

import re

from variantcourt.domain import NormalizedVariant

_TRANSCRIPT_HGVS = re.compile(r"^(?P<tx>[NX][MR]_\d+(?:\.\d+)?)\s*[:\s]\s*(?P<hgvs>[cgnp]\..+)$")
# [cgn] only: a gene-level p. name is a protein change, handled by _GENE_PROTEIN below.
_GENE_HGVS = re.compile(r"^(?P<gene>[A-Za-z0-9\-]+)\s*[:\s]\s*(?P<hgvs>[cgn]\..+)$")
_RSID = re.compile(r"^rs\d+$", re.IGNORECASE)
# Clinician shorthand: BRAF V600E, TP53 R248W, CFTR F508del, BRCA1 p.Glu23ValfsTer17
_GENE_PROTEIN = re.compile(
    r"^(?P<gene>[A-Za-z][A-Za-z0-9\-]{1,14})\s*[: ]\s*(?P<prot>p\.\S+|[A-Z]\d+(?:[A-Z*]|del|dup|fs|ins\w*|Ter)\w*)$"
)

_AA1_TO_3 = {
    "A": "Ala", "R": "Arg", "N": "Asn", "D": "Asp", "C": "Cys", "Q": "Gln", "E": "Glu", "G": "Gly",
    "H": "His", "I": "Ile", "L": "Leu", "K": "Lys", "M": "Met", "F": "Phe", "P": "Pro", "S": "Ser",
    "T": "Thr", "W": "Trp", "Y": "Tyr", "V": "Val", "X": "Ter", "*": "Ter",
}


def protein_to_hgvs_p(prot: str) -> str:
    """V600E -> p.Val600Glu; F508del -> p.Phe508del. Already-HGVS input passes through."""
    if prot.startswith("p."):
        return prot
    m = re.fullmatch(r"([A-Z])(\d+)([A-Z*])", prot)
    if m and m.group(1) in _AA1_TO_3 and m.group(3) in _AA1_TO_3:
        return f"p.{_AA1_TO_3[m.group(1)]}{m.group(2)}{_AA1_TO_3[m.group(3)]}"
    m = re.fullmatch(r"([A-Z])(\d+)(del|dup|fs|Ter)(\w*)", prot)
    if m and m.group(1) in _AA1_TO_3:
        return f"p.{_AA1_TO_3[m.group(1)]}{m.group(2)}{m.group(3)}{m.group(4)}"
    return prot


_PAREN_GENE = re.compile(r"^([NX][MR]_\d+(?:\.\d+)?)\s*\(([A-Za-z0-9\-]+)\)\s*:")


def normalize_variant(raw: str, assembly: str = "GRCh38") -> NormalizedVariant:
    text = raw.strip()
    gene = None
    if m := _PAREN_GENE.match(text):  # ClinVar style: NM_004333.6(BRAF):c.1799T>A
        gene = m.group(2).upper()
        text = f"{m.group(1)}:{text[m.end():].strip()}"
    if m := _TRANSCRIPT_HGVS.match(text):
        return NormalizedVariant(
            input=raw,
            gene=gene,
            transcript=m.group("tx"),
            hgvs=m.group("hgvs").strip(),
            assembly=assembly,
        )
    if _RSID.match(text):
        return NormalizedVariant(input=raw, rsid=text.lower(), assembly=assembly)
    if m := _GENE_HGVS.match(text):
        return NormalizedVariant(
            input=raw,
            gene=m.group("gene").upper(),
            hgvs=m.group("hgvs").strip(),
            assembly=assembly,
        )
    if m := _GENE_PROTEIN.match(text):
        # Protein-level name; the clerk resolves it to transcript HGVS via ClinVar.
        return NormalizedVariant(
            input=raw,
            gene=m.group("gene").upper(),
            protein_change=protein_to_hgvs_p(m.group("prot")),
            assembly=assembly,
        )
    return NormalizedVariant(input=raw, assembly=assembly)


def variant_key(v: NormalizedVariant) -> str:
    """Stable lookup key for fixtures/caches."""
    if v.gene and v.protein_change and not v.hgvs:
        return f"{v.gene}:{v.protein_change}"
    if v.transcript and v.hgvs:
        return f"{v.transcript}:{v.hgvs}"
    if v.gene and v.hgvs:
        return f"{v.gene}:{v.hgvs}"
    if v.rsid:
        return v.rsid
    return v.input.strip()
