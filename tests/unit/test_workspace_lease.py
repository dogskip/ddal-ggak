from __future__ import annotations

from pathlib import Path

import pytest

from ddk.services.workspace_lease import WorkspaceLease


def test_lease_observes_real_directory_and_releases_only_after_cleanup():
    observed = []
    paths = []

    def changed(record):
        observed.append(record)
        if record["state"] == "released":
            assert paths and not paths[0].exists()

    with WorkspaceLease("a" * 64, "candidate", 1, changed) as folder:
        paths.append(Path(folder))
        assert paths[0].is_dir()
        assert observed[0]["state"] == "active"
        (paths[0] / "file").write_text("private")
    assert [r["state"] for r in observed] == ["active", "released"]
    assert observed[0]["lease_id"] == observed[1]["lease_id"]


def test_cleanup_failure_never_produces_a_release_receipt(monkeypatch):
    import tempfile

    observed = []
    original = tempfile.TemporaryDirectory.cleanup

    def failed(self):
        original(self)
        raise OSError("simulated cleanup confirmation failure")

    monkeypatch.setattr(tempfile.TemporaryDirectory, "cleanup", failed)
    with pytest.raises(OSError), WorkspaceLease("a" * 64, "candidate", 0, observed.append):
        pass
    assert [r["state"] for r in observed] == ["active", "cleanup_failed"]
