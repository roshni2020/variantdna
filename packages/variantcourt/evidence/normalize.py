"""Variant input normalization. Small and forgiving; the Evidence Clerk refines it."""

from __future__ import annotations

import re

from variantcourt.domain import NormalizedVariant

_TRANSCRIPT_HGVS = re.compile(r"^(?P<tx>[NX][MR]_\d+(?:\.\d+)?)\s*[:\s]\s*(?P<hgvs>[cgnp]\..+)$")
_GENE_HGVS = re.compile(r"^(?P<gene>[A-Za-z0-9\-]+)\s*[:\s]\s*(?P<hgvs>[cgnp]\..+)$")
_RSID = re.compile(r"^rs\d+$", re.IGNORECASE)


def normalize_variant(raw: str, assembly: str = "GRCh38") -> NormalizedVariant:
    text = raw.strip()
    if m := _TRANSCRIPT_HGVS.match(text):
        return NormalizedVariant(
            input=raw,
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
    return NormalizedVariant(input=raw, assembly=assembly)


def variant_key(v: NormalizedVariant) -> str:
    """Stable lookup key for fixtures/caches."""
    if v.transcript and v.hgvs:
        return f"{v.transcript}:{v.hgvs}"
    if v.gene and v.hgvs:
        return f"{v.gene}:{v.hgvs}"
    if v.rsid:
        return v.rsid
    return v.input.strip()
