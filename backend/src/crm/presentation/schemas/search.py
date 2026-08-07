from __future__ import annotations

from pydantic import BaseModel

from crm.presentation.schemas.clients import ClientListItemOut
from crm.presentation.schemas.orders import OrderListItemOut
from crm.presentation.schemas.tracks import TrackOut


class SearchOut(BaseModel):
    clients: list[ClientListItemOut]
    orders: list[OrderListItemOut]
    tracks: list[TrackOut]
