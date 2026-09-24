"""Restore the enrolled user's state directories before a scheduled tick."""

import os
import sys


def run(args: list[str]) -> int:
    if len(args) != 3:
        return 2
    organization_id, config_directory, data_directory = args
    os.environ["XDG_CONFIG_HOME"] = config_directory
    os.environ["XDG_DATA_HOME"] = data_directory
    from ai_stp_cli.app import main

    return main(["heartbeat", "tick", "--organization", organization_id, "--json"])


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
