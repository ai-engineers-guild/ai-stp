"""Worker entrypoint: build the runner, wire signals and run until drained."""

from __future__ import annotations

import asyncio
import signal

from ai_stp_platform.db import make_engine, make_sessionmaker
from ai_stp_platform.logging import configure_logging
from ai_stp_worker.runner import Worker
from ai_stp_worker.settings import Settings, load_settings


def _install_signals(worker: Worker) -> None:
    loop = asyncio.get_running_loop()

    def _handle_signal(_signum: int, _frame: object | None) -> None:
        worker.request_stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, worker.request_stop)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, _handle_signal)


async def _run(settings: Settings) -> None:
    engine = make_engine(settings.database)
    sessionmaker = make_sessionmaker(engine)
    worker = Worker(
        sessionmaker,
        worker_id=settings.worker.worker_id,
        batch_size=settings.worker.batch_size,
        poll_interval_seconds=settings.worker.poll_interval_seconds,
    )
    _install_signals(worker)
    try:
        await worker.run()
    finally:
        await engine.dispose()


def main() -> None:
    """Load settings, configure logging and run the worker."""
    settings = load_settings()
    configure_logging(settings.worker.log_dir)
    asyncio.run(_run(settings))


if __name__ == "__main__":
    main()
