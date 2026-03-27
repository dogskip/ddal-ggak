from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DDKBaseModel(BaseModel):
    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        populate_by_name=True,
        extra="forbid",
    )
