"""Serve both user-docs languages the way production does.

Russian is the site root. English is `/en/`. `mkdocs serve` can host only one
docs_dir, so the language switcher 404s on a Russian-only live server. This
script builds both lines into `.site-user-docs` (Russian first, so it can
clean the directory) and serves that tree. Optional polling rebuilds when
Markdown under `docs-user-facing/docs` changes.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
DOCS = ROOT / "docs-user-facing" / "docs"
SITE = ROOT / ".site-user-docs"
RU_YML = SCRIPTS / "user-mkdocs.yml"
EN_YML = SCRIPTS / "user-mkdocs.en.yml"


def _stamp(root: Path) -> tuple[tuple[str, int, int], ...]:
    rows: list[tuple[str, int, int]] = []
    for path in root.rglob("*"):
        if path.is_file():
            stat = path.stat()
            rows.append((path.as_posix(), stat.st_mtime_ns, stat.st_size))
    rows.sort()
    return tuple(rows)


def build() -> None:
    python = sys.executable
    for config in (RU_YML, EN_YML):
        subprocess.run(
            [python, "-m", "mkdocs", "build", "--strict", "-f", str(config)],
            check=True,
            cwd=ROOT,
        )


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(SITE), **kwargs)  # type: ignore[misc]

    def log_message(self, format: str, *args: object) -> None:
        message = format % args
        sys.stderr.write(f"{self.address_string()} - {message}\n")


def serve(host: str, port: int) -> ThreadingHTTPServer:
    SITE.mkdir(parents=True, exist_ok=True)
    return ThreadingHTTPServer((host, port), _Handler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("USER_DOCS_DEV_HOST", "0.0.0.0"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("USER_DOCS_DEV_PORT", "8000")),
    )
    parser.add_argument("--watch", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--poll", type=float, default=2.0)
    args = parser.parse_args()

    build()
    httpd = serve(args.host, args.port)
    print(f"serving {SITE} at http://{args.host}:{args.port}/ and /en/", flush=True)

    if not args.watch:
        httpd.serve_forever()
        return 0

    import threading

    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    previous = _stamp(DOCS)
    while True:
        time.sleep(args.poll)
        current = _stamp(DOCS)
        if current == previous:
            continue
        previous = current
        print("docs changed; rebuilding both languages", flush=True)
        try:
            build()
        except subprocess.CalledProcessError as exc:
            print(f"rebuild failed: {exc}", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
