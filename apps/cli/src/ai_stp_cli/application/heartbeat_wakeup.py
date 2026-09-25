"""Restore the enrolled user's state directories before a scheduled tick."""

import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


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
    from ai_stp_cli.app import main

    with (
        Path(os.devnull).open("w", encoding="utf-8") as sink,
        redirect_stdout(sink),
        redirect_stderr(sink),
    ):
        return main(["heartbeat", "tick", "--organization", organization_id, "--json"])


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
