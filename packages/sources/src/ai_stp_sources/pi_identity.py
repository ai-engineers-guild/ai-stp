"""Pi skill visibility and prompt names over the captured tree only."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping

from pathspec import GitIgnoreSpec
from pathspec.patterns.gitignore import GitIgnorePatternError

from ai_stp_sources.native_frontmatter import invalid, parse
from ai_stp_sources.native_markdown import captured


def identities(kind: str, files: Mapping[str, bytes]) -> dict[str, list[str]]:
    entries = captured(files, (".pi/", ".agents/"), ("skills/" if kind == "skill" else "prompts/",))
    result: dict[str, list[str]] = {path: [] for path in files}
    if kind == "command":
        for local, (path, payload) in entries.items():
            if "/" not in local and local.endswith(".md"):
                parse(payload, optional=True, merged=False)
                result[path] = [local[:-3]]
        return result
    children: dict[str, set[str]] = defaultdict(set)
    for local in entries:
        child = local
        while "/" in child:
            parent = child.rsplit("/", 1)[0]
            children[parent].add(child)
            child = parent
        children[""].add(child)
    rules: list[str] = []
    matcher = GitIgnoreSpec.from_lines(rules)

    def add_rules(directory: str) -> None:
        nonlocal matcher
        prefix = directory + "/" if directory else ""
        before = len(rules)
        for name in (".gitignore", ".ignore", ".fdignore"):
            entry = entries.get(prefix + name)
            if entry is None:
                continue
            payload = entry[1]
            if len(payload) > 64 * 1024:
                raise invalid()
            try:
                lines = payload.decode("utf-8").split("\n")
            except UnicodeError as error:
                raise invalid() from error
            for line in lines:
                line = line.removesuffix("\r")
                if not line.strip() or line.strip().startswith("#"):
                    continue
                if len(line.encode()) > 4096 or len(rules) >= 10_000:
                    raise invalid()
                negative = "!" if line.startswith("!") else ""
                pattern = line[1:] if negative else line.removeprefix("\\!")
                # The upstream matcher is case-insensitive on every platform;
                # scoped rules accumulate in deterministic traversal order.
                rules.append((negative + prefix + pattern.removeprefix("/")).lower())
        if len(rules) != before:
            try:
                matcher = GitIgnoreSpec.from_lines(rules)
            except GitIgnorePatternError as error:
                raise invalid() from error

    def skill(local: str, *, declared: bool) -> None:
        path, payload = entries[local]
        header = parse(payload, optional=True, merged=False)
        description = header.get("description")
        if not isinstance(description, str) or not description.strip():
            if declared:
                raise invalid()
            return
        parent = local.rsplit("/", 1)[0].rsplit("/", 1)[-1] if "/" in local else "skills"
        name = header.get("name")
        result[path] = [name if isinstance(name, str) and name else parent]

    def scan(directory: str) -> None:
        if directory.count("/") >= 32:
            raise invalid()
        add_rules(directory)
        declared = (directory + "/" if directory else "") + "SKILL.md"
        if declared in entries and not matcher.match_file(declared.lower()):
            skill(declared, declared=True)
            return
        for local in sorted(children.get(directory, ())):
            leaf = local.rsplit("/", 1)[-1]
            if leaf.startswith(".") or leaf == "node_modules":
                continue
            is_directory = local not in entries
            if matcher.match_file(local.lower() + ("/" if is_directory else "")):
                continue
            if is_directory:
                scan(local)
            elif not directory and leaf.endswith(".md"):
                skill(local, declared=False)

    scan("")
    return result
