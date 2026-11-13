"""Verify admission originals against reviewed, repository-pinned receipts."""

import hashlib
import json
from datetime import datetime
from urllib.parse import urlsplit

# A reviewed receipt pins the role, HTTPS URI, exact bytes and capture time.
# No qualifying registry/scratch originals are currently available for pinning.
_REVIEWED_RECEIPTS: frozenset[tuple[str, str, str, datetime]] = frozenset()


def verified_original(
    role: str, uri: str, digest: str, observed: datetime, original: bytes | None, cutoff: datetime,
) -> dict | None:
    """Require both matching bytes and an independently reviewed capture receipt."""
    if not isinstance(observed, datetime) or observed.utcoffset() is None or observed > cutoff or not isinstance(original, bytes):
        return None
    if hashlib.sha256(original).hexdigest() != digest:
        return None
    try:
        endpoint = urlsplit(uri)
        if (endpoint.scheme != "https" or not endpoint.hostname or endpoint.username is not None
                or endpoint.hostname == "rikstoto.no" or endpoint.hostname.endswith(".rikstoto.no")
                or (role == "ATG_HISTORY" and endpoint.hostname != "www.atg.se")
                or (role, uri, digest, observed) not in _REVIEWED_RECEIPTS):
            return None
        doc = json.loads(original)
    except (ValueError, UnicodeError, RecursionError):
        return None
    return doc if isinstance(doc, dict) else None
