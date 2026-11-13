"""Prepare the native Go vulnerability database for local-only govulncheck."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import zipfile
from datetime import UTC, datetime
from pathlib import Path

_ENTRY = re.compile(r"(?:index/[A-Za-z0-9_.-]+|ID/GO-[0-9]{4}-[0-9]+)\.json")
_INDEXES = ("index/db.json", "index/modules.json", "index/vulns.json")


def prepare(archive: Path, destination: Path, max_bytes: int, max_files: int) -> None:
    if max_bytes <= 0 or max_files <= 0:
        raise ValueError("Go database limits must be positive.")
    destination.mkdir(parents=True, exist_ok=False)
    indexes: dict[str, object] = {}
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        names = {entry.filename for entry in entries}
        if len(entries) > max_files or len(names) != len(entries):
            raise ValueError("Go database has too many or duplicate entries.")
        if not set(_INDEXES) <= names:
            raise ValueError("Go database indexes are missing.")
        if sum(entry.file_size for entry in entries) > max_bytes:
            raise ValueError("Go database exceeds its unpacked byte limit.")
        for entry in entries:
            if not _ENTRY.fullmatch(entry.filename) or stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError("Go database contains an unsupported archive member.")
            data = bundle.read(entry)
            document: object = json.loads(data)
            if entry.filename in _INDEXES:
                indexes[entry.filename] = document
            elif not isinstance(document, dict) or document.get("id") != Path(entry.filename).stem:
                raise ValueError("Go vulnerability record identity does not match its path.")
            target = destination / entry.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    metadata = indexes["index/db.json"]
    if not isinstance(metadata, dict) or not isinstance(metadata.get("modified"), str):
        raise ValueError("Go database metadata is invalid.")
    for name in _INDEXES[1:]:
        if not isinstance(indexes[name], list):
            raise ValueError("Go database index is invalid.")
    refreshed = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    (destination / ".ai_stp_osv_refreshed_at").write_text(refreshed + "\n", encoding="utf-8")
    with archive.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    (destination / "STATUS.txt").write_text(
        f"refreshed_at_utc={refreshed}\narchive_sha256={digest}\nfiles={len(entries)}\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("max_bytes", type=int)
    parser.add_argument("max_files", type=int)
    arguments = parser.parse_args()
    prepare(arguments.archive, arguments.destination, arguments.max_bytes, arguments.max_files)


if __name__ == "__main__":
    main()
