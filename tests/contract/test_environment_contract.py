"""`.env.prod.example` is the environment contract, so it must be complete.

`SPEC-024` `REQ-2402` says the contract is stated by the example files, and that
a missing required secret is a typed refusal to start rather than a silent
default. Both halves are already true. What was not checked is the step before
them: that the example actually names every setting the deployment cannot start
without.

That gap is invisible until a deployment. The real `.env.prod` lives on the host
and is excluded from transfer on purpose, so it drifts from the example silently
and nothing in this repository can correct it. An operator reconciles the two by
hand, from the example — so a required setting the example never mentions is a
setting the host will never have, and the typed refusal arrives in production
instead of in review.

The names are derived from the settings classes rather than restated here: a
list of expected variables in a test is a second source that can disagree with
the first.
"""

import inspect
import re
from pathlib import Path

from pydantic_settings import BaseSettings

from ai_stp_api import settings as api_settings
from ai_stp_platform import settings as platform_settings
from ai_stp_worker import settings as worker_settings

EXAMPLE = Path(__file__).parents[2] / ".env.prod.example"

# Named by `REQ-2402` and consumed by the web tier, which is TypeScript and
# therefore has no pydantic model to derive them from.
WEB_REQUIRED = (
    "AI_STP_API_BASE_URL",
    "NEXT_PUBLIC_APP_URL",
    "AI_STP_USER_DOCS_URL",
    "AI_STP_WEB_PROFILE",
    "AI_STP_SESSION_SECRET",
)


def _declared_names() -> set[str]:
    text = EXAMPLE.read_text(encoding="utf-8")
    return {
        match.group(1)
        for match in re.finditer(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=", text, flags=re.MULTILINE)
    }


def _required_settings() -> dict[str, str]:
    required: dict[str, str] = {}
    for module in (api_settings, platform_settings, worker_settings):
        for _name, obj in vars(module).items():
            if not inspect.isclass(obj):
                continue
            if not issubclass(obj, BaseSettings) or obj is BaseSettings:
                continue
            prefix = obj.model_config.get("env_prefix", "")
            for field, info in obj.model_fields.items():
                if info.is_required():
                    required[f"{prefix}{field}".upper()] = obj.__name__
    return required


def test_every_required_setting_is_named_in_the_prod_example() -> None:
    declared = _declared_names()
    missing = {
        variable: owner
        for variable, owner in _required_settings().items()
        if variable not in declared
    }

    assert not missing, (
        "settings with no default are absent from .env.prod.example, so an "
        f"operator reconciling the host by hand cannot know to set them: {missing}"
    )


def test_the_example_names_the_web_variables_the_requirement_lists() -> None:
    declared = _declared_names()

    assert set(WEB_REQUIRED) <= declared
