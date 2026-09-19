"""Private registry sync. Effects live in `application.sync`."""

from ai_stp_cli.application import sync as _service
from ai_stp_cli.application.sync import commit_merge, merge, preview, pull, push


def __getattr__(name: str) -> object:
    return getattr(_service, name)


__all__ = ["commit_merge", "merge", "preview", "pull", "push"]
