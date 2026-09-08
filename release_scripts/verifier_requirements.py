"""Export the isolated provider verifier's locked runtime dependencies."""

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "apps/cli/src/ai_stp_cli/provider/verifier-requirements.txt"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = subprocess.run(
        [
            "uv",
            "export",
            "--locked",
            "--only-group",
            "provider-verifier",
            "--no-emit-workspace",
            "--no-header",
            "--no-annotate",
            "--format",
            "requirements-txt",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    if args.check:
        if not DESTINATION.is_file() or DESTINATION.read_text() != result.stdout:
            print("provider verifier requirements differ from uv.lock; run just back-gen")
            return 1
    else:
        DESTINATION.write_text(result.stdout, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
