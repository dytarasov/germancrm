from __future__ import annotations

from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter, Depends

from crm.application.services.track_service import TrackService
from crm.presentation.auth import require_auth
from crm.presentation.mappers.api_mappers import suggestion_to_out, track_to_out
from crm.presentation.schemas.tracks import (
    SuggestionOut,
    TrackAssign,
    TrackCreate,
    TrackOut,
    TrackUpdate,
)

router = APIRouter(
    prefix="/api/tracks",
    tags=["tracks"],
    route_class=DishkaRoute,
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[TrackOut])
async def list_tracks(
    svc: FromDishka[TrackService],
    unmatched: bool | None = None,
    search: str | None = None,
) -> list[TrackOut]:
    return [track_to_out(t) for t in await svc.list(unmatched=unmatched, search=search)]


@router.post("", response_model=TrackOut, status_code=201)
async def create_track(payload: TrackCreate, svc: FromDishka[TrackService]) -> TrackOut:
    track = await svc.create(
        tracking_number=payload.tracking_number,
        carrier=payload.carrier,
        order_id=payload.order_id,
        note=payload.note,
    )
    return track_to_out(track)


@router.patch("/{track_id}", response_model=TrackOut)
async def update_track(
    track_id: int, payload: TrackUpdate, svc: FromDishka[TrackService]
) -> TrackOut:
    track = await svc.update(track_id, payload.model_dump(exclude_unset=True))
    return track_to_out(track)


@router.post("/{track_id}/assign", response_model=TrackOut)
async def assign_track(
    track_id: int, payload: TrackAssign, svc: FromDishka[TrackService]
) -> TrackOut:
    return track_to_out(await svc.assign(track_id, payload.order_id))


@router.post("/{track_id}/dismiss", response_model=TrackOut)
async def dismiss_track(track_id: int, svc: FromDishka[TrackService]) -> TrackOut:
    return track_to_out(await svc.dismiss(track_id))


@router.get("/{track_id}/suggestions", response_model=list[SuggestionOut])
async def track_suggestions(
    track_id: int, svc: FromDishka[TrackService]
) -> list[SuggestionOut]:
    return [suggestion_to_out(c) for c in await svc.suggestions(track_id)]


@router.delete("/{track_id}", status_code=204)
async def delete_track(track_id: int, svc: FromDishka[TrackService]) -> None:
    await svc.delete(track_id)
