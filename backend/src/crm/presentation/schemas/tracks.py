from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TrackCreate(BaseModel):
    tracking_number: str = Field(min_length=1)
    carrier: str | None = None
    order_id: int | None = None
    note: str | None = None


class OrderTrackCreate(BaseModel):
    tracking_number: str = Field(min_length=1)
    carrier: str | None = None
    note: str | None = None


class TrackAssign(BaseModel):
    order_id: int | None


class TrackUpdate(BaseModel):
    tracking_number: str | None = Field(default=None, min_length=1)
    carrier: str | None = None
    note: str | None = None


class TrackCandidateOut(BaseModel):
    order_id: int
    score: int
    reasons: list[str]
    order_label: str


class TrackOut(BaseModel):
    id: int
    tracking_number: str
    carrier: str | None
    order_id: int | None
    suborder_id: int | None
    source: str
    match_status: str
    candidates: list[TrackCandidateOut] | None
    note: str | None
    created_at: datetime


class SuggestionOut(BaseModel):
    order_id: int
    order_label: str
    client_name: str
    score: int
    reasons: list[str]
