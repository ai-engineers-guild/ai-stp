"""Keep immutable release coordinates separate from untrusted GitHub responses."""

from __future__ import annotations

import copy
import hashlib
import sys
from dataclasses import replace
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / ".github/scripts/released-previous-native-cli.py"
PAYLOAD = b"synthetic archive bytes, never an executable\n"


@pytest.fixture
def module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = spec_from_file_location("released_previous_native_fixture", SCRIPT)
    assert spec is not None and spec.loader is not None
    loaded = module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, loaded)
    spec.loader.exec_module(loaded)
    return loaded


def install_metadata(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, schema: int
) -> tuple[Any, dict[str, dict[str, Any] | bytes], list[tuple[str, bool]]]:
    # Real immutable coordinates; only the unit's inert archive bytes differ.
    release = replace(
        module.RELEASES[schema],
        archive_bytes=len(PAYLOAD),
        archive_sha256=hashlib.sha256(PAYLOAD).hexdigest(),
    )
    responses: dict[str, dict[str, Any] | bytes] = {
        f"git/ref/tags/{release.tag}": {
            "object": {"sha": release.tag_object, "type": "tag", "url": "synthetic-ref"}
        },
        f"git/tags/{release.tag_object}": {
            "tag": release.tag,
            "object": {"sha": release.source, "type": "commit"},
        },
        f"git/commits/{release.source}": {"tree": {"sha": release.tree}},
        f"releases/tags/{release.tag}": {
            "tag_name": release.tag,
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "id": release.asset_id,
                    "name": release.archive_name,
                    "size": release.archive_bytes,
                    "digest": "sha256:" + release.archive_sha256,
                }
            ],
        },
        f"releases/assets/{release.asset_id}": PAYLOAD,
    }
    calls: list[tuple[str, bool]] = []

    def observe(path: str, *, binary: bool = False) -> Any:
        calls.append((path, binary))
        response = responses[path]
        assert isinstance(response, bytes) is binary
        return copy.deepcopy(response)

    monkeypatch.setattr(module, "api", observe)
    return release, responses, calls


@pytest.mark.parametrize("schema", [60, 61])
def test_release_metadata_does_not_replace_the_immutable_descriptor(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, schema: int
) -> None:
    release, responses, calls = install_metadata(module, monkeypatch, schema)
    before = copy.deepcopy(responses)
    assert module.archive(release) == PAYLOAD
    assert responses == before
    assert calls == [(path, isinstance(value, bytes)) for path, value in responses.items()]
    assert release.tag == f"cli-v{module.RELEASES[schema].version}"


@pytest.mark.parametrize("schema", [60, 61])
@pytest.mark.parametrize("change", ["tag", "source", "tree", "asset", "digest", "payload"])
def test_release_refuses_changed_coordinates_or_downloaded_bytes(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, schema: int, change: str
) -> None:
    release, responses, _calls = install_metadata(module, monkeypatch, schema)
    if change == "payload":
        responses[f"releases/assets/{release.asset_id}"] = b"changed bytes"
    else:
        paths = {
            "tag": f"releases/tags/{release.tag}",
            "source": f"git/tags/{release.tag_object}",
            "tree": f"git/commits/{release.source}",
            "asset": f"releases/tags/{release.tag}",
            "digest": f"releases/tags/{release.tag}",
        }
        value = responses[paths[change]]
        assert isinstance(value, dict)
        if change == "tag":
            value["tag_name"] = "cli-v0.0.0"
        elif change == "source":
            value["object"]["sha"] = "0" * 40
        elif change == "tree":
            value["tree"]["sha"] = "0" * 40
        elif change == "asset":
            value["assets"][0]["id"] += 1
        else:
            value["assets"][0]["digest"] = "sha256:" + "0" * 64
    with pytest.raises(AssertionError):
        module.archive(release)
