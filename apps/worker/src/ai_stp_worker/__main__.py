"""Worker entrypoint: build the runner, wire signals and run until drained."""

from __future__ import annotations

import asyncio
import contextlib
import signal

from pydantic import ValidationError

from ai_stp_platform.corporate_mail import (
    DEFAULT_CONFIRM_TEMPLATE,
    CorporateMailTemplateLoader,
    ResendCorporateMailPort,
    SmtpCorporateMailPort,
)
from ai_stp_platform.db import make_engine, make_sessionmaker
from ai_stp_platform.logging import configure_logging, get_logger
from ai_stp_platform.mail import ResendMailPort, SmtpConfig, SmtpMailPort
from ai_stp_platform.settings import StorageSettings
from ai_stp_platform.storage.s3 import S3ObjectClient
from ai_stp_worker.handlers import deliver_corporate_invitation, deliver_invitation
from ai_stp_worker.runner import Worker
from ai_stp_worker.settings import Settings, WorkerSettings, load_settings

_log = get_logger("worker_main")


def _install_signals(worker: Worker) -> None:
    loop = asyncio.get_running_loop()

    def _handle_signal(_signum: int, _frame: object | None) -> None:
        worker.request_stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, worker.request_stop)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, _handle_signal)


def _load_storage_settings() -> StorageSettings | None:
    """Optional S3 access for mail templates; absent config means embedded only."""
    try:
        return StorageSettings()  # pyright: ignore[reportCallIssue]
    except ValidationError:
        return None


def select_mail_provider(worker: WorkerSettings) -> str:
    """Resolve the delivery provider: explicit setting, else the auto order.

    auto = Resend when an API key is present (hosted delivery), else SMTP
    when a relay host is configured (company SMTP / self-hosted MTA /
    Mailpit), else the recording port — nothing leaves the host.
    """
    if worker.mail_provider != "auto":
        return worker.mail_provider
    if worker.corporate_resend_api_key or worker.resend_api_key:
        return "resend"
    if worker.smtp_host:
        return "smtp"
    return "recording"


def _configure_mail_ports(worker: WorkerSettings) -> None:
    """Wire the invitation mail ports for the resolved provider."""
    provider = select_mail_provider(worker)
    if provider == "smtp":
        smtp = SmtpConfig(
            host=worker.smtp_host,
            port=worker.smtp_port,
            username=worker.smtp_username,
            password=worker.smtp_password,
            use_tls=worker.smtp_use_tls,
            use_starttls=worker.smtp_use_starttls,
        )
        deliver_invitation.MAIL_PORT = SmtpMailPort(
            smtp=smtp,
            from_address=worker.mail_from_address,
            accept_base_url=worker.invitation_base_url,
        )
        deliver_corporate_invitation.MAIL_PORT = SmtpCorporateMailPort(
            smtp=smtp,
            from_address=worker.corporate_mail_from_address,
        )
    elif provider == "resend":
        if worker.resend_api_key:
            deliver_invitation.MAIL_PORT = ResendMailPort(
                api_key=worker.resend_api_key,
                from_address=worker.mail_from_address,
                accept_base_url=worker.invitation_base_url,
            )
        corporate_key = worker.corporate_resend_api_key or worker.resend_api_key
        if corporate_key:
            deliver_corporate_invitation.MAIL_PORT = ResendCorporateMailPort(
                api_key=corporate_key,
                from_address=worker.corporate_mail_from_address,
            )
    else:
        # Recording: mails stay in process memory — invitations are created
        # but never reach the recipient's inbox.
        _log.warning(
            "mail_delivery_unconfigured",
            detail="no mail provider configured; invitations are recorded only",
        )
    _log.info("mail_provider_selected", provider=provider)


async def _run(settings: Settings) -> None:
    _configure_mail_ports(settings.worker)
    deliver_corporate_invitation.ACCEPT_BASE_URL = settings.worker.invitation_base_url

    async with contextlib.AsyncExitStack() as stack:
        storage = _load_storage_settings()
        if storage is not None:
            object_client = await stack.enter_async_context(S3ObjectClient(storage))
            template_bucket = (
                settings.worker.corporate_mail_template_bucket or storage.asset_bucket_name
            )
            deliver_corporate_invitation.TEMPLATE_LOADER = CorporateMailTemplateLoader(
                client=object_client,
                bucket=template_bucket,
                key=settings.worker.corporate_mail_template_key,
            )
            deliver_corporate_invitation.CONFIRM_TEMPLATE_LOADER = CorporateMailTemplateLoader(
                client=object_client,
                bucket=template_bucket,
                key=settings.worker.corporate_mail_confirm_template_key,
                fallback=DEFAULT_CONFIRM_TEMPLATE,
            )
        engine = make_engine(settings.database)
        stack.push_async_callback(engine.dispose)
        sessionmaker = make_sessionmaker(engine)
        worker = Worker(
            sessionmaker,
            worker_id=settings.worker.worker_id,
            batch_size=settings.worker.batch_size,
            poll_interval_seconds=settings.worker.poll_interval_seconds,
            drain_timeout_seconds=settings.worker.drain_timeout_seconds,
            lease_timeout_seconds=settings.worker.lease_timeout_seconds,
            heartbeat_interval_seconds=settings.worker.heartbeat_interval_seconds,
        )
        _install_signals(worker)
        await worker.run()


def main() -> None:
    """Load settings, configure logging and run the worker."""
    settings = load_settings()
    configure_logging(settings.worker.log_dir)
    asyncio.run(_run(settings))


if __name__ == "__main__":
    main()
