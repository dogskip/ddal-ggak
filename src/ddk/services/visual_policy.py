"""Whether a case must come with screenshot evidence."""

from __future__ import annotations


def visual_required(case_input: object | None) -> bool:
    """Image-based cases need a screenshot comparison unless the run waived it."""
    has_images = bool(getattr(case_input, "image_paths", []))
    return has_images and bool(getattr(case_input, "visual_check", True))


def visual_waived(case_input: object | None) -> bool:
    return bool(getattr(case_input, "image_paths", [])) and not bool(
        getattr(case_input, "visual_check", True)
    )
