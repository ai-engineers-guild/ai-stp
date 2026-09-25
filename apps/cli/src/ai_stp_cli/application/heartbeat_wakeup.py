"""Restore the enrolled user's state directories before a scheduled tick."""

import os
import sys


def run(args: list[str]) -> int:
    if len(args) != 4 or args[3] not in {"0", "1"}:
        return 2
    organization_id, config_directory, data_directory, file_credentials = args
    os.environ["XDG_CONFIG_HOME"] = config_directory
    os.environ["XDG_DATA_HOME"] = data_directory
    if file_credentials == "1":
        os.environ["AI_STP_FORCE_FILE_CREDENTIAL_STORE"] = "1"
    else:
        os.environ.pop("AI_STP_FORCE_FILE_CREDENTIAL_STORE", None)
    from ai_stp_cli.application.heartbeat import maybe_send_due

    maybe_send_due(organization_id=organization_id, scheduled=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
