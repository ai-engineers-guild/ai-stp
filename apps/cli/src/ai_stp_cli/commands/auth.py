"""`ai-stp auth` — Click handlers. Effects live in `application.auth`."""

from ai_stp_cli.application import auth as _service
from ai_stp_cli.application.auth import (
    PROVIDERS,
    begin,
    complete,
    endpoint,
    logout,
)


def __getattr__(name: str) -> object:
    return getattr(_service, name)


__all__ = ["PROVIDERS", "begin", "complete", "endpoint", "logout"]
