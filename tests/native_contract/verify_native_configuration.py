"""Real offline CLI lifecycle in a disposable OS-user/PID namespace.

The coordinator deliberately ignores HOME/state environment selectors. Bubblewrap
supplies an isolated OS account database instead; the host user's store is unused.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from ai_stp_foundation.digests import digest_canonical


def qualify(binary: Path, root: Path) -> None:
    for name in ("home", "state", "target", "source"):
        (root / name).mkdir(mode=0o700)
    (root / "passwd").write_text("root:x:0:0:Native fixture:/tmp/home:/bin/sh\n")
    (root / "group").write_text("root:x:0:\n")
    (root / "source/guide.md").write_text("# Native guidance\nVerify affected behavior.\n")
    (root / "target/user-note").write_text("unowned file stays\n")
    prefix = [
        "/usr/bin/bwrap", "--unshare-user", "--uid", "0", "--gid", "0",
        "--unshare-pid", "--unshare-net", "--die-with-parent", "--new-session",
        "--ro-bind", "/", "/", "--proc", "/proc", "--dev", "/dev",
        "--ro-bind", str(root / "passwd"), "/etc/passwd", "--ro-bind", str(root / "group"), "/etc/group",
        "--bind", str(root), "/tmp", "--chdir", "/tmp",
        "--clearenv", "--setenv", "PATH", "", "--setenv", "HOME", "/decoy",
        "--setenv", "USERPROFILE", "/decoy", "--setenv", "XDG_DATA_HOME", "/decoy",
        str(binary),
    ]

    def run(*args: str, expected: int = 0) -> dict[str, Any]:
        result = subprocess.run(
            [*prefix, *args, *([] if args[:2] == ("context", "apply") else ["--state-dir", "/tmp/state"]), "--json"],
            capture_output=True, timeout=60, check=False,
        )
        assert result.returncode == expected, (args, result.stdout.decode(), result.stderr.decode())
        assert not result.stderr, result.stderr.decode()
        reply = json.loads(result.stdout)
        assert reply["ok"] == (expected == 0), reply
        return reply["data"] if expected == 0 else reply

    def enact(data: dict[str, Any], *args: str) -> dict[str, Any]:
        name = f"plan-{len(list(root.glob('plan-*.json')))}.json"
        (root / name).write_text(json.dumps(data["plan"]))
        return run(*args, "--plan", f"/tmp/{name}", "--plan-digest", data["plan_digest"])

    run("init", "--credential-store", "file")
    contexts = []
    for label in ("Original personal", "Second view"):
        plan = run("context", "create", "plan", "--label", label)
        contexts.append(plan["plan"]["change"]["context"]["context_id"])
        enact(plan, "context", "apply")
    author_input = {"schema_version": 1, "directory": "/tmp/source", "harness_id": "codex",
                    "component_type": "instruction", "name": "native-fixture", "license_spdx": "MIT"}
    (root / "author.json").write_text(json.dumps(author_input))
    author = run("task", "start", "--intent", "author", "--idempotency-key", "native-cli-author-fixture-0001", "--input", "/tmp/author.json")
    assert author["state"] == "completed", author
    setup_id = author["outcome"]["setup_id"]
    version = run("local", "version", "show", "--kind", "setup", "--id", setup_id, "--version", "1.0")

    def passport(value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            if value.get("kind") == "setup" and value.get("stable_id") == setup_id:
                return value
            for nested in value.values():
                found = passport(nested)
                if found is not None:
                    return found
        return None

    document = passport(version)
    assert document is not None, version
    request = {"schema_version": 1, "setup": {"stable_id": setup_id, "version": "1.0",
               "passport_digest": digest_canonical("ai-stp:passport:v1", document)},
               "harness_id": "codex", "operation": "install", "roots": {"global": "/tmp/target"}}
    (root / "request.json").write_text(json.dumps(request))
    reviewed = run("configuration", "plan", "--context", contexts[0], "--input", "/tmp/request.json")
    assert not (root / "target/AGENTS.md").exists()
    operation, digest = reviewed["plan"]["operation_id"], reviewed["plan_digest"]
    prepared = enact(reviewed, "configuration", "prepare")
    assert prepared["configuration_changed"] is False
    assert not (root / "target/AGENTS.md").exists()
    selected = run("context", "select", "plan", "--context", contexts[1])
    enact(selected, "context", "apply")
    pending = run("configuration", "pending")["pending"]
    assert pending["operation_id"] == operation and pending["plan_digest"] == digest
    assert pending["original_context"]["context_id"] == contexts[0]
    applied = run("configuration", "apply", "--operation", operation, "--plan-digest", digest)
    assert applied["original_context"]["context_id"] == contexts[0]
    assert applied["load_state"] == "not_observed"
    assert "Native guidance" in (root / "target/AGENTS.md").read_text()
    assert run("configuration", "apply", "--operation", operation, "--plan-digest", digest) == applied
    assert not run("configuration", "effective", "--context", contexts[1])["setups"]
    assert len(run("configuration", "effective", "--context", contexts[0])["setups"]) == 1
    removed_plan = run("configuration", "remove", "plan", "--operation", operation, "--plan-digest", digest)
    removal, removal_digest = removed_plan["plan"]["operation_id"], removed_plan["plan_digest"]
    enact(removed_plan, "configuration", "prepare")
    run("configuration", "apply", "--operation", removal, "--plan-digest", removal_digest)
    assert not (root / "target/AGENTS.md").exists()
    assert (root / "target/user-note").read_text() == "unowned file stays\n"
    assert (root / "target/.codex-setup-system/journal.json").is_file()
    assert run("context", "list")["selected"]["context_id"] == contexts[1]
    assert not run("configuration", "effective", "--context", contexts[0])["setups"]
    assert not (root / "home/.local/share/ai-stp-custody").is_symlink()
    print(json.dumps({"native_cli_lifecycle": "passed", "original_context": True,
                      "offline_os_user_namespace": True, "unowned_preserved": True}))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="ai-stp-native-cli-") as temporary:
        qualify(Path(sys.argv[1]).resolve(), Path(temporary))
