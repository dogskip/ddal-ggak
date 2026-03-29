"""FailureClassifier — maps raw error strings to FAILURE_TAXONOMY IDs. VALID-05.

Pure logic: no I/O, no async, no external dependencies beyond ddk.models.validation.
"""

from __future__ import annotations

import re
import uuid

from ddk.models.validation import FailureRecord

# (regex_pattern, taxonomy_id, severity)
# Ordered: more specific patterns first, broader patterns last.
_RULES: list[tuple[str, str, str]] = [
    # Build failures
    (
        r"Cannot find module|Module not found|Failed to resolve",
        "FT-BUILD-001",
        "critical",
    ),
    (
        r"SyntaxError|Unexpected token|Unexpected end of|Unexpected identifier",
        "FT-BUILD-002",
        "critical",
    ),
    (
        r"is not a module|has no exported member|does not provide an export",
        "FT-BUILD-003",
        "major",
    ),
    # Type errors
    (
        r"is not assignable to type|Cannot find name|Type .* is not",
        "FT-TYPE-001",
        "major",
    ),
    (
        r"implicitly has an .any. type|lacks return.type annotation|Parameter .* implicitly",
        "FT-TYPE-002",
        "minor",
    ),
    (r"Incompatible type|type mismatch", "FT-TYPE-003", "major"),
    # Lint
    (
        r"Unused variable|Unused import|is defined but never used|no-unused",
        "FT-LINT-001",
        "minor",
    ),
    (
        r"Expected.*semicolon|Parsing error|Expected .*token|Missing semicolon",
        "FT-LINT-002",
        "minor",
    ),
    (r"naming.convention|camelCase|PascalCase|SCREAMING_SNAKE", "FT-LINT-003", "minor"),
    # Runtime — null ref before unhandled rejection (more specific first)
    (
        r"Uncaught TypeError|Cannot read propert|Cannot read properties of null|null is not",
        "FT-RUNTIME-002",
        "critical",
    ),
    (
        r"Unhandled.*rejection|UnhandledPromise|UnhandledRejection|unhandledRejection",
        "FT-RUNTIME-001",
        "critical",
    ),
    (
        r"404|503|Failed to fetch|net::ERR_|ECONNREFUSED|request.*failed",
        "FT-RUNTIME-003",
        "major",
    ),
    # Visual
    (r"Layout shift|Cumulative Layout|CLS score", "FT-VISUAL-001", "major"),
    (r"color.*mismatch|mismatch.*color|expected.*color", "FT-VISUAL-002", "minor"),
    (r"element.*missing|missing.*element|not found in DOM", "FT-VISUAL-003", "minor"),
    # Data
    (r"data.binding|binding.*fail|prop.*undefined|undefined.*prop", "FT-DATA-001", "major"),
    (r"missing.*prop|required.*prop|prop.*required", "FT-DATA-002", "minor"),
    # Async
    (r"race condition|concurrent|TOCTOU", "FT-ASYNC-001", "major"),
    (
        r"await.*not.*async|async.*missing.*await|Promise.*not.*await|unresolved.*promise",
        "FT-ASYNC-002",
        "major",
    ),
]


class FailureClassifier:
    """Maps raw error strings to FAILURE_TAXONOMY IDs. Pure logic — no I/O.

    Usage:
        classifier = FailureClassifier()
        record = classifier.classify("Cannot find module './Button'")
        # record.taxonomy_id == "FT-BUILD-001"
    """

    def classify(self, raw_message: str, file_path: str | None = None) -> FailureRecord:
        """Classify a raw error message and return a FailureRecord with stable taxonomy_id.

        Always returns a FailureRecord — never raises, never returns None.
        Unrecognized messages get taxonomy_id='FT-UNKNOWN'.

        Args:
            raw_message: Raw error string from build/type/lint/runtime tools.
            file_path: Optional source file path to attach to the record.

        Returns:
            FailureRecord with stable taxonomy_id from FAILURE_TAXONOMY, or 'FT-UNKNOWN'.
        """
        for pattern, taxonomy_id, severity in _RULES:
            if re.search(pattern, raw_message, re.IGNORECASE):
                return FailureRecord(
                    id=str(uuid.uuid4()),
                    taxonomy_id=taxonomy_id,
                    severity=severity,  # type: ignore[arg-type]
                    message=raw_message[:500],
                    file_path=file_path,
                    raw_output=raw_message,
                )
        return FailureRecord(
            id=str(uuid.uuid4()),
            taxonomy_id="FT-UNKNOWN",
            severity="major",
            message=raw_message[:500],
            file_path=file_path,
            raw_output=raw_message,
        )
