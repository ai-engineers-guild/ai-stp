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


# A setting with a default is never "missing" to the test above, and that is
# right for most of them: an unset value falls back to something that works.
# `admin_account_ids` is the exception in kind, not in degree. Its default is
# the empty string, and empty does not mean "the usual staff" — it means nobody,
# so the whole staff surface refuses every account, the operator's included.
# The lane that needs it then stays closed silently: `authoritative` requires
# `author_verified`, only this surface grants it, and an operator watching a
# published catalogue sit entirely in `experimental` has no reason to suspect an
# environment variable.
#
# Both places an operator would look must therefore name it, and the runbook is
# the one that matters: it is where somebody goes to *do* the grant, and until
# now it described the policy of granting without mentioning that the mechanism
# is inert by default.
STAFF_GATE = "AI_STP_AUTH_ADMIN_ACCOUNT_IDS"
AUTHOR_VERIFICATION_RUNBOOK = (
    Path(__file__).parents[2] / "docs/operations/runbooks/author-verification.md"
)


def test_the_example_names_the_variable_that_opens_the_staff_surface() -> None:
    assert STAFF_GATE in _declared_names(), (
        f"{STAFF_GATE} is absent from .env.prod.example, so a deployment "
        "reconciled from it has an inert staff surface and a permanently "
        "experimental catalogue"
    )


def test_the_grant_runbook_names_what_makes_the_grant_possible() -> None:
    runbook = AUTHOR_VERIFICATION_RUNBOOK.read_text(encoding="utf-8")

    assert STAFF_GATE in runbook, (
        "the author-verification runbook tells an owner to grant "
        f"author_verified without naming {STAFF_GATE}, which every path to the "
        "grant goes through; an owner following it on a fresh deployment is "
        "refused with nothing pointing at the cause"
    )
