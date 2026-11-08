"""Keep OSV findings visible and separate RustSec maintenance notices from vulnerabilities."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("expected an OSV object")
    return value


def _items(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("expected an OSV list")
    return value


def maintenance_notice(advisory: dict[str, Any], package: dict[str, Any]) -> bool:
    """Only authoritative, unscored RustSec unmaintained metadata is informational.

    Unknown severity, a matching title or an absent fix never makes a vulnerability
    informational. A CVE, severity score or security category keeps it blocking.
    """
    identifier = advisory.get("id")
    if (
        not isinstance(identifier, str)
        or not identifier.startswith("RUSTSEC-")
        or package.get("ecosystem") != "crates.io"
        or advisory.get("severity")
        or any(str(alias).startswith("CVE-") for alias in _items(advisory.get("aliases") or []))
    ):
        return False
    affected = [
        _object(item)
        for item in _items(advisory.get("affected", []))
        if _object(_object(item).get("package", {})).get("name") == package.get("name")
        and _object(_object(item).get("package", {})).get("ecosystem") == "crates.io"
    ]
    return bool(affected) and all(
        _object(item.get("database_specific", {})).get("informational") == "unmaintained"
        and _object(item.get("database_specific", {})).get("cvss") is None
        and not _object(item.get("database_specific", {})).get("categories")
        for item in affected
    )


def assess(report: Any, scanner_status: int, source: str) -> tuple[int, dict[str, Any]]:
    """Preserve the full report; incomplete or failed scans cannot become green."""
    if scanner_status not in (0, 1):
        raise ValueError(f"OSV scanner failed with exit status {scanner_status}")
    report = _object(report)
    if "results" not in report:
        raise ValueError("OSV report is missing results")
    results = _items(report["results"] if report["results"] is not None else [])
    maintenance = vulnerabilities = 0
    for value in results:
        result = _object(value)
        # Reports may be published by CI. Keep the caller's repository-relative
        # lockfile name instead of a machine's absolute checkout path.
        _object(result["source"])["path"] = source
        for entry in _items(result["packages"]):
            entry = _object(entry)
            package = _object(entry["package"])
            if not all(
                isinstance(package.get(key), str) and package[key] for key in ("name", "ecosystem")
            ):
                raise ValueError("OSV package has no name or ecosystem")
            for advisory in _items(entry.get("vulnerabilities", [])):
                advisory = _object(advisory)
                if not isinstance(advisory.get("id"), str):
                    raise ValueError("OSV advisory has no identifier")
                if maintenance_notice(advisory, package):
                    maintenance += 1
                else:
                    vulnerabilities += 1
    if scanner_status == 1 and not (maintenance or vulnerabilities):
        raise ValueError("OSV reported findings without inspectable advisories")
    return int(vulnerabilities > 0), {
        "source": source,
        "maintenance_notices": maintenance,
        "vulnerabilities": vulnerabilities,
        "osv": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("scanner_status", type=int)
    parser.add_argument("source")
    args = parser.parse_args()
    try:
        status, report = assess(
            json.loads(args.report.read_text(encoding="utf-8")), args.scanner_status, args.source
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"dependency report refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
