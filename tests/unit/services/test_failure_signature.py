"""failure_signature: identity of a failure set, used to detect an auto-fix loop going nowhere."""

from __future__ import annotations

import subprocess
import sys
import uuid

from ddk.models.validation import FailureRecord
from ddk.services.failure_signature import failure_signature


def _failure(
    message: str = "Type 'string' is not assignable to type 'number'.",
    *,
    taxonomy_id: str = "FT-TYPE-001",
    file_path: str | None = "src/App.tsx",
    line: int | None = 4,
    code: str | None = "TS2322",
) -> FailureRecord:
    return FailureRecord(
        id=str(uuid.uuid4()),
        taxonomy_id=taxonomy_id,
        severity="major",
        message=message,
        file_path=file_path,
        line_number=line,
        code=code,
    )


def test_fresh_ids_do_not_change_the_signature() -> None:
    assert failure_signature([_failure()]) == failure_signature([_failure()])


def test_order_does_not_matter() -> None:
    a, b = _failure("first"), _failure("second")

    assert failure_signature([a, b]) == failure_signature([b, a])


def test_fixing_one_of_several_errors_in_a_file_is_visible() -> None:
    before = [_failure("error one"), _failure("error two"), _failure("error three")]
    after = before[1:]

    assert failure_signature(before) != failure_signature(after)


def test_a_different_message_in_the_same_file_is_a_different_failure() -> None:
    assert failure_signature([_failure("alpha")]) != failure_signature([_failure("beta")])


def test_moving_to_another_line_is_still_the_same_failure() -> None:
    assert failure_signature([_failure(line=4)]) == failure_signature([_failure(line=9)])


def test_different_file_or_code_is_a_different_failure() -> None:
    base = failure_signature([_failure()])

    assert base != failure_signature([_failure(file_path="src/Other.tsx")])
    assert base != failure_signature([_failure(code="TS2345")])


def test_empty_set_has_a_signature() -> None:
    assert isinstance(failure_signature([]), int)


def test_signature_is_stable_across_interpreter_runs() -> None:
    """Python's built-in hash() of str is salted per process; this must not be."""
    program = (
        "from ddk.models.validation import FailureRecord;"
        "from ddk.services.failure_signature import failure_signature;"
        "f=FailureRecord(id='x',taxonomy_id='FT-TYPE-001',severity='major',message='m',"
        "file_path='a.ts',code='TS1');"
        "print(failure_signature([f]))"
    )
    outputs = {
        subprocess.run(
            [sys.executable, "-c", program],
            capture_output=True,
            text=True,
            check=True,
            env={"PYTHONHASHSEED": seed, "PATH": ""},
        ).stdout.strip()
        for seed in ("1", "2", "3")
    }

    assert len(outputs) == 1
