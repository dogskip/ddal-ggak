"""IntakeProcessor — validates CaseInput and extracts image metadata (INGEST-02)."""

from __future__ import annotations

import hashlib

from ddk.models.input import CaseInput


class IntakeProcessor:
    """Validates CaseInput, checks image paths exist, computes image hashes."""

    async def process(self, case_input: CaseInput) -> tuple[CaseInput, dict[str, str]]:
        """Validate input and compute image hashes.

        Args:
            case_input: User-provided case input.

        Returns:
            Tuple of (validated CaseInput, image_hashes dict mapping str(path) → SHA256[:16]).

        Raises:
            FileNotFoundError: If any image_path does not exist.
        """
        image_hashes: dict[str, str] = {}
        for img_path in case_input.image_paths:
            if not img_path.exists():
                raise FileNotFoundError(f"Image not found: {img_path}")
            img_bytes = img_path.read_bytes()
            hash_hex = hashlib.sha256(img_bytes).hexdigest()[:16]
            image_hashes[str(img_path)] = hash_hex

        return case_input, image_hashes
