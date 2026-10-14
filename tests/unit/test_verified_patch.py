from __future__ import annotations

import json

import pytest

from ddk.services.source_snapshot import SourceSnapshot, manifest_digest
from ddk.services.verified_repair import RepairReply, _propose
from tests.unit.test_verified_change_engine import fixed_file


def source(content=b"alpha\nbeta\n"):
    files = (fixed_file("src/app.py", content),)
    return SourceSnapshot(files, manifest_digest(files))


def propose(patches, current=None):
    text = json.dumps({"patches": patches})
    return _propose(
        RepairReply(text, False, len(text.encode())),
        current or source(),
        {"src/app.py"},
        {"limits": {"max_changed_files": 10, "max_file_bytes": 1024, "max_artifact_bytes": 2048}},
    )


def test_search_replace_preserves_other_bytes_and_changes_hash():
    before = source()
    after = propose(
        [{"path": "src/app.py", "hunks": [{"search": "beta", "replace": "gamma"}]}], before
    )
    assert after.files[0].content == b"alpha\ngamma\n"
    assert before.files[0].content == b"alpha\nbeta\n" and after.tree_sha256 != before.tree_sha256


@pytest.mark.parametrize(
    ("search", "replacement", "content"),
    [
        ("absent", "x", b"alpha"),
        ("a", "x", b"aa"),
        ("", "x", b"alpha"),
        ("alpha", "alpha", b"alpha"),
    ],
)
def test_ambiguous_missing_empty_and_unchanged_hunks_are_rejected(search, replacement, content):
    with pytest.raises(ValueError):
        propose(
            [{"path": "src/app.py", "hunks": [{"search": search, "replace": replacement}]}],
            source(content),
        )
