from __future__ import annotations

from collections.abc import AsyncIterable

import asyncpg
import httpx
from dishka import Provider, Scope, provide

from crm.application.interfaces.gdrive import DrivePort
from crm.application.interfaces.gmail import GmailPort
from crm.application.interfaces.llm import LLMExtractor
from crm.application.interfaces.repositories import (
    ClientRepository,
    DashboardRepository,
    EmailRepository,
    FlightRepository,
    GmailStateRepository,
    LoginBanRepository,
    OrderItemRepository,
    OrderRepository,
    PaymentRepository,
    ReportRepository,
    SettingsRepository,
    StatusHistoryRepository,
    TrackRepository,
)
from crm.application.interfaces.uow import UnitOfWork
from crm.application.services.auth_service import AuthService
from crm.application.services.client_service import ClientService
from crm.application.services.dashboard_service import DashboardService
from crm.application.services.flight_service import FlightService
from crm.application.services.mail_service import MailService
from crm.application.services.matching import MatcherService
from crm.application.services.order_service import OrderService
from crm.application.services.payment_service import PaymentService
from crm.application.services.report_service import ReportService
from crm.application.services.security_service import SecurityService
from crm.application.services.settings_service import SettingsService
from crm.application.services.track_service import TrackService
from crm.infrastructure.config import Settings
from crm.infrastructure.db.pool import create_pool
from crm.infrastructure.db.uow import AsyncpgUnitOfWork
from crm.infrastructure.gdrive.client import GoogleDriveClient
from crm.infrastructure.gmail.client import GmailApiClient
from crm.infrastructure.llm.client import NullLLM, OpenRouterLLM
from crm.infrastructure.repositories.client_repo import PgClientRepository
from crm.infrastructure.repositories.dashboard_repo import PgDashboardRepository
from crm.infrastructure.repositories.email_repo import PgEmailRepository
from crm.infrastructure.repositories.flight_repo import PgFlightRepository
from crm.infrastructure.repositories.gmail_state_repo import PgGmailStateRepository
from crm.infrastructure.repositories.login_ban_repo import PgLoginBanRepository
from crm.infrastructure.repositories.order_item_repo import PgOrderItemRepository
from crm.infrastructure.repositories.order_repo import PgOrderRepository
from crm.infrastructure.repositories.payment_repo import PgPaymentRepository
from crm.infrastructure.repositories.report_repo import PgReportRepository
from crm.infrastructure.repositories.settings_repo import PgSettingsRepository
from crm.infrastructure.repositories.status_history_repo import PgStatusHistoryRepository
from crm.infrastructure.repositories.track_repo import PgTrackRepository


class AppProvider(Provider):
    scope = Scope.APP

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    @provide
    def settings(self) -> Settings:
        return self._settings

    @provide
    async def http_client(self) -> AsyncIterable[httpx.AsyncClient]:
        async with httpx.AsyncClient() as client:
            yield client

    @provide
    async def pool(self, settings: Settings) -> AsyncIterable[asyncpg.Pool]:
        pool = await create_pool(settings.database_dsn)
        yield pool
        await pool.close()

    @provide
    def auth_service(self, settings: Settings) -> AuthService:
        return AuthService(
            password=settings.app_password,
            secret=settings.secret_key,
            ttl_days=settings.session_ttl_days,
        )

    @provide
    def matcher(self) -> MatcherService:
        return MatcherService()

    @provide
    def gmail(self, http: httpx.AsyncClient, settings: Settings) -> GmailPort:
        return GmailApiClient(
            http,
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
            redirect_uri=f"{settings.public_base_url}/api/mail/oauth/callback",
        )

    @provide
    def drive(self, http: httpx.AsyncClient) -> DrivePort:
        return GoogleDriveClient(http)


class RequestProvider(Provider):
    scope = Scope.REQUEST

    @provide
    async def connection(self, pool: asyncpg.Pool) -> AsyncIterable[asyncpg.Connection]:
        async with pool.acquire() as conn:
            yield conn

    uow = provide(AsyncpgUnitOfWork, provides=UnitOfWork)

    clients = provide(PgClientRepository, provides=ClientRepository)
    orders = provide(PgOrderRepository, provides=OrderRepository)
    order_items = provide(PgOrderItemRepository, provides=OrderItemRepository)
    tracks = provide(PgTrackRepository, provides=TrackRepository)
    payments = provide(PgPaymentRepository, provides=PaymentRepository)
    flights = provide(PgFlightRepository, provides=FlightRepository)
    history = provide(PgStatusHistoryRepository, provides=StatusHistoryRepository)
    dashboard = provide(PgDashboardRepository, provides=DashboardRepository)
    reports = provide(PgReportRepository, provides=ReportRepository)
    settings_repo = provide(PgSettingsRepository, provides=SettingsRepository)
    gmail_state = provide(PgGmailStateRepository, provides=GmailStateRepository)
    emails = provide(PgEmailRepository, provides=EmailRepository)
    login_bans = provide(PgLoginBanRepository, provides=LoginBanRepository)

    client_service = provide(ClientService)
    order_service = provide(OrderService)
    track_service = provide(TrackService)
    payment_service = provide(PaymentService)
    flight_service = provide(FlightService)
    dashboard_service = provide(DashboardService)
    report_service = provide(ReportService)
    settings_service = provide(SettingsService)
    security_service = provide(SecurityService)

    @provide
    def llm(
        self,
        http: httpx.AsyncClient,
        settings: Settings,
        settings_repo: SettingsRepository,
    ) -> LLMExtractor:
        if settings.openrouter_api_key:
            return OpenRouterLLM(
                http,
                settings_repo,
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_base_url,
            )
        return NullLLM()

    @provide
    def mail_service(
        self,
        gmail: GmailPort,
        gmail_state: GmailStateRepository,
        emails: EmailRepository,
        settings_repo: SettingsRepository,
        orders: OrderRepository,
        tracks: TrackRepository,
        order_service: OrderService,
        matcher: MatcherService,
        llm: LLMExtractor,
        uow: UnitOfWork,
        settings: Settings,
        drive: DrivePort,
    ) -> MailService:
        return MailService(
            gmail,
            gmail_state,
            emails,
            settings_repo,
            orders,
            tracks,
            order_service,
            matcher,
            llm,
            uow,
            gmail_configured=settings.gmail_configured,
            drive=drive,
            backups_dir=settings.backups_dir,
        )
