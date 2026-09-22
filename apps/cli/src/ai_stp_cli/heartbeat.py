"""Corporate installation heartbeat payload rules (t-heartbeat, #215).

A separate channel from the anonymous, consented telemetry ping
(`telemetry.py`, ADR-0112): heartbeats travel authenticated `/v1/corporate/`
requests bound to the session's account and device. The closed field set is
the whole payload - `cli_version`, `capabilities`, `last_sync_at`, the
reported `health_state`, `checked_at`, and the session-bound references.
The token alphabet below exists so a path, an environment value, or a secret
can never fit inside a capability string.
"""

import re

CAPABILITY_TOKEN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}(@[A-Za-z0-9][A-Za-z0-9.+_-]{0,63})?$")
REPORTED_STATES = ("active", "failing", "disabled")
MAX_CAPABILITIES = 64


def capability_token(value: str) -> str:
    """Return `value` when it is a heartbeat capability token, else raise."""
    if CAPABILITY_TOKEN.fullmatch(value) is None:
        raise ValueError("not a heartbeat capability token")
    return value
