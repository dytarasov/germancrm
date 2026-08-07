from __future__ import annotations

from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter, Depends

from crm.application.services.flight_service import FlightService
from crm.domain.clock import business_today
from crm.presentation.auth import require_auth
from crm.presentation.mappers.api_mappers import flight_detail_to_out, flight_to_out
from crm.presentation.schemas.flights import (
    FlightCreate,
    FlightDetailOut,
    FlightOut,
    FlightUpdate,
)

router = APIRouter(
    prefix="/api/flights",
    tags=["flights"],
    route_class=DishkaRoute,
    dependencies=[Depends(require_auth)],
)


@router.post("", response_model=FlightOut, status_code=201)
async def create_flight(payload: FlightCreate, svc: FromDishka[FlightService]) -> FlightOut:
    flight = await svc.create(
        departed_on=payload.departed_on,
        cost_usd=payload.cost_usd,
        description=payload.description,
    )
    return flight_to_out(flight)


@router.get("", response_model=list[FlightOut])
async def list_flights(svc: FromDishka[FlightService]) -> list[FlightOut]:
    return [flight_to_out(f) for f in await svc.list()]


@router.get("/{flight_id}", response_model=FlightDetailOut)
async def get_flight(flight_id: int, svc: FromDishka[FlightService]) -> FlightDetailOut:
    return flight_detail_to_out(await svc.get_detail(flight_id), business_today())


@router.patch("/{flight_id}", response_model=FlightOut)
async def update_flight(
    flight_id: int, payload: FlightUpdate, svc: FromDishka[FlightService]
) -> FlightOut:
    flight = await svc.update(flight_id, payload.model_dump(exclude_unset=True))
    return flight_to_out(flight)


@router.delete("/{flight_id}", status_code=204)
async def delete_flight(flight_id: int, svc: FromDishka[FlightService]) -> None:
    await svc.delete(flight_id)
