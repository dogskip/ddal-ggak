"""Private archive paths are components, not substrings of public skill names."""

from __future__ import annotations

import zipfile

import pytest
from scripts.check_wheel import FORBIDDEN_PARTS, REQUIRED, problems


def archive(path, extra=()):
    with zipfile.ZipFile(path, "w") as output:
        for name in [*REQUIRED, *extra]:
            output.writestr(name, b"")


def test_public_evidence_skill_is_a_required_distribution_asset(tmp_path):
    wheel = tmp_path / "valid.whl"
    archive(wheel)
    assert problems(wheel) == []


@pytest.mark.parametrize("part", FORBIDDEN_PARTS)
@pytest.mark.parametrize("prefix", ["", "nested/"])
def test_every_protected_directory_stays_rejected(tmp_path, part, prefix):
    wheel = tmp_path / "invalid.whl"
    private = prefix + part + "private.txt"
    archive(wheel, [private])
    assert f"must not be in the distribution: {private}" in problems(wheel)
