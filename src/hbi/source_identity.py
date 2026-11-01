"""Conservative source-name validation shared by CORE-003 research gates.

A positional field placeholder is not a stable horse identity, even when two
Rikstoto source views contain the same text. Observed in ORIGINAL Milano
2026-11-01, S3 races 7 and 8: "Häst 1" etc. The lexical detector is narrow;
not proof that every name outside this grammar is independently verified.
"""
from __future__ import annotations

import re
import unicodedata


_PLACEHOLDER = re.compile(r"(?:hast|horse|cavallo|cheval)(?:[1-9]|[12]\d|30)\Z")


def is_generic_horse_identity(value: object) -> bool:
    """True for standalone generic "Häst N"/"Horse N" etc, N=1..30."""
    if not isinstance(value, str):
        return False
    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.encode("ascii", "ignore").decode("ascii").casefold()
    token = re.sub(r"[^a-z0-9]", "", normalized)
    return bool(_PLACEHOLDER.fullmatch(token))
