"""Courtroom agents, one file each:

- evidence_clerk.py     Evidence Clerk (gathers/normalizes evidence, never classifies)
- pathogenic_counsel.py Pathogenic Counsel
- benign_counsel.py     Benign Counsel
- cross_examiner.py     TypeSafe Cross-Examiner
- jury.py               Judge / Jury
"""

from .base import CounselAgent, JuryAgent, claim_id
from .benign_counsel import LLMBenignCounsel, MockBenignCounsel
from .cross_examiner import MockTypeSafeProvider, TypeSafeAPIProvider, TypeSafeProvider
from .evidence_clerk import EvidenceClerk, LiveEvidenceClerk, MockEvidenceClerk, assemble_state
from .jury import LLMJury, MockJury
from .pathogenic_counsel import LLMPathogenicCounsel, MockPathogenicCounsel

__all__ = [
    "CounselAgent",
    "EvidenceClerk",
    "JuryAgent",
    "LiveEvidenceClerk",
    "LLMBenignCounsel",
    "LLMJury",
    "LLMPathogenicCounsel",
    "MockBenignCounsel",
    "MockEvidenceClerk",
    "MockJury",
    "MockPathogenicCounsel",
    "MockTypeSafeProvider",
    "TypeSafeAPIProvider",
    "TypeSafeProvider",
    "assemble_state",
    "claim_id",
]
