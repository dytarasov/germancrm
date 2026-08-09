from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class LoginBanOut(BaseModel):
    ip: str
    fails: int
    last_fail_at: datetime
    banned_until: datetime | None
