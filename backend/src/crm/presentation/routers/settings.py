from __future__ import annotations

from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter, Depends

from crm.application.interfaces.llm import LLMExtractor, LLMUnavailableError, LLMValidationError
from crm.application.services.settings_service import SettingsService
from crm.presentation.auth import require_auth
from crm.presentation.mappers.api_mappers import settings_view_to_out
from crm.presentation.schemas.settings import LlmTestOut, SettingsOut, SettingsPatch

router = APIRouter(
    prefix="/api/settings",
    tags=["settings"],
    route_class=DishkaRoute,
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=SettingsOut)
async def get_settings(svc: FromDishka[SettingsService]) -> SettingsOut:
    return settings_view_to_out(await svc.view())


@router.patch("", response_model=SettingsOut)
async def patch_settings(
    payload: SettingsPatch, svc: FromDishka[SettingsService]
) -> SettingsOut:
    view = await svc.patch(payload.model_dump(exclude_unset=True))
    return settings_view_to_out(view)


@router.post("/llm-test", response_model=LlmTestOut)
async def llm_test(llm: FromDishka[LLMExtractor]) -> LlmTestOut:
    try:
        model = await llm.ping()
    except LLMUnavailableError as exc:
        return LlmTestOut(ok=False, model=None, message=str(exc))
    except LLMValidationError as exc:
        return LlmTestOut(ok=False, model=None, message=f"Модель отвечает некорректно: {exc}")
    return LlmTestOut(ok=True, model=model, message="Модель отвечает")
