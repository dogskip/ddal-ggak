"""failure_signature — identity of a failure set for auto-fix loop control. VALID-04.

Failure ``id`` values are fresh UUIDs on every run and line numbers drift when code is
edited, so neither can identify "the same failure". The signature uses what survives a
fix attempt: taxonomy, file, tool code and message. It is a sha256 digest, so it is the
same in every interpreter run (``hash()`` of a str is salted per process).
"""

from __future__ import annotations

import hashlib

from ddk.models.validation import FailureRecord


def failure_signature(failures: list[FailureRecord]) -> int:
    """Return a 60-bit signature that is equal for equal failure sets."""
    identities = sorted(
        {(f.taxonomy_id, f.file_path or "", f.code or "", f.message.strip()) for f in failures}
    )
    digest = hashlib.sha256(repr(identities).encode("utf-8")).hexdigest()
    return int(digest[:15], 16)
