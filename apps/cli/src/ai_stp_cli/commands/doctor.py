"""`ai-stp doctor` — the setup state, reported rather than judged (issue #72).

`doctor` exits `0` even when the installation is not ready. An installation that
has merely not been set up yet is the normal state right after `uv tool install`,
and answering non-zero would make the first run look broken and break any caller
running under `set -e`. The state is in the body, where a reader can act on it;
`SPEC-011` names the four values.

A non-zero exit is reserved for `doctor` itself failing — the difference between
"I looked and you are not ready" and "I could not look".
"""

from collections.abc import Mapping

from ai_stp_cli.answer import Answer
from ai_stp_cli.application.inspect import doctor as inspect_doctor
from ai_stp_cli.application.inspect import worst
from ai_stp_contracts.machine_help import DoctorReport

__all__ = ["run", "worst"]


def run(_parameters: Mapping[str, object]) -> Answer[DoctorReport]:
    """Look at everything this build can look at, and say what was found."""
    return Answer(inspect_doctor())
