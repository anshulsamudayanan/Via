"""Shared request/response schemas."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

DEFAULT_LIMIT = 25
MAX_LIMIT = 100

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 320 or not _EMAIL_RE.match(value):
        raise ValueError("Enter a valid email address.")
    return value


#: Trimmed, lower-cased, syntactically plausible email address.
Email = Annotated[str, AfterValidator(_normalize_email)]


def _clean_text(value: str) -> str:
    value = value.strip()
    if any(ord(c) < 32 for c in value):
        raise ValueError("Control characters are not allowed.")
    return value


Name = Annotated[str, AfterValidator(_clean_text), Field(min_length=1, max_length=120)]


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page[T](APIModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class PageParams(BaseModel):
    limit: int = Field(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    offset: int = Field(0, ge=0)
