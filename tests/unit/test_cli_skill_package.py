"""The Agent Skills authoring contract (`#455`).

Every limit asserted here is quoted from <https://agentskills.io/specification>,
not chosen in this repository. That is the whole reason `skill` went first of
the closed kinds: it is the one where the validator can be wrong about something
other than our own opinion, and these tests are what makes that checkable.
"""

from pathlib import Path

import pytest

from ai_stp_cli.local import skill_package

BODY = "\n# A skill\n\nDo the thing.\n"


def _package(root: Path, name: str, **frontmatter: str) -> Path:
    place = root / name
    place.mkdir(parents=True, exist_ok=True)
    fields = {"name": name, "description": "Does a thing. Use when a thing is needed."}
    fields.update(frontmatter)
    lines = "\n".join(f"{key}: {value}" for key, value in fields.items() if value != "\x00")
    (place / "SKILL.md").write_text(f"---\n{lines}\n---\n{BODY}", encoding="utf-8")
    return place


def test_a_conforming_package_is_accepted_with_no_findings(tmp_path: Path) -> None:
    place = _package(tmp_path, "pdf-processing")
    (place / "scripts").mkdir()
    (place / "references").mkdir()
    report = skill_package.validate(place)
    assert report.conforms
    assert report.findings == ()
    assert report.name == "pdf-processing"
    assert report.standard_directories == ("references", "scripts")


def test_the_entry_point_must_be_at_the_root(tmp_path: Path) -> None:
    """ "A skill is a directory containing, at minimum, a `SKILL.md` file."

    A `payload/` wrapper makes the package non-conforming for every reader that
    implements the standard rather than ours, which is exactly the failure this
    kind was chosen to make checkable.
    """
    wrapped = tmp_path / "wrapped"
    inner = _package(wrapped, "payload")
    assert inner.exists()
    report = skill_package.validate(wrapped)
    assert not report.conforms
    assert [item.code for item in report.findings] == ["SK002"]
    assert "not inside payload/" in report.findings[0].summary


@pytest.mark.parametrize(
    ("name", "code"),
    [
        # "May only contain unicode lowercase alphanumeric characters and
        # hyphens"; "must not start or end with a hyphen"; "must not contain
        # consecutive hyphens". The last is the one an obvious regex allows.
        ("PDF-Processing", "SK012"),
        ("-pdf", "SK012"),
        ("pdf-", "SK012"),
        ("pdf--processing", "SK012"),
        ("pdf_processing", "SK012"),
    ],
)
def test_a_name_outside_the_specified_character_rules_is_refused(
    tmp_path: Path, name: str, code: str
) -> None:
    place = tmp_path / name
    place.mkdir()
    (place / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Does a thing.\n---\n{BODY}", encoding="utf-8"
    )
    report = skill_package.validate(place)
    assert code in {item.code for item in report.findings}


def test_a_name_longer_than_the_limit_is_refused(tmp_path: Path) -> None:
    long = "a" * (skill_package.NAME_MAX + 1)
    report = skill_package.validate(_package(tmp_path, long))
    assert "SK011" in {item.code for item in report.findings}


def test_the_name_must_match_the_directory(tmp_path: Path) -> None:
    """ "Must match the parent directory name."

    Two names for one skill is how a package installs under one and is referred
    to by the other.
    """
    place = _package(tmp_path, "on-disk")
    (place / "SKILL.md").write_text(
        f"---\nname: in-frontmatter\ndescription: Does a thing.\n---\n{BODY}", encoding="utf-8"
    )
    report = skill_package.validate(place)
    assert "SK013" in {item.code for item in report.findings}


def test_a_missing_or_oversized_description_is_refused(tmp_path: Path) -> None:
    empty = _package(tmp_path, "no-description", description="")
    assert "SK020" in {item.code for item in skill_package.validate(empty).findings}

    huge = _package(
        tmp_path, "long-description", description="x" * (skill_package.DESCRIPTION_MAX + 1)
    )
    assert "SK021" in {item.code for item in skill_package.validate(huge).findings}


def test_the_optional_fields_are_checked_only_where_the_standard_constrains_them(
    tmp_path: Path,
) -> None:
    """`license` has no stated limit, so none is invented; `compatibility` has one."""
    lenient = _package(tmp_path, "licensed", license="Proprietary. LICENSE.txt has full terms")
    assert skill_package.validate(lenient).conforms

    over = _package(
        tmp_path, "incompatible", compatibility="y" * (skill_package.COMPATIBILITY_MAX + 1)
    )
    assert "SK030" in {item.code for item in skill_package.validate(over).findings}


def test_metadata_must_be_a_map_of_strings(tmp_path: Path) -> None:
    place = tmp_path / "metadata-skill"
    place.mkdir()
    (place / "SKILL.md").write_text(
        "---\nname: metadata-skill\ndescription: Does a thing.\n"
        "metadata:\n  version: 1.0\n---\n" + BODY,
        encoding="utf-8",
    )
    # `1.0` parses as a float, and the standard says string values.
    assert "SK031" in {item.code for item in skill_package.validate(place).findings}


def test_a_plugin_under_the_same_parent_is_not_reported_as_a_broken_skill(
    tmp_path: Path,
) -> None:
    """Two kinds live under `skills/`, told apart by manifest and not by location.

    A validator that does not know this reports a perfectly good plugin as a
    skill with no entry point, and sends its author to fix the wrong file.
    """
    for manifest in (
        tmp_path / "rooted" / "plugin.json",
        tmp_path / "vendored" / ".claude-plugin" / "plugin.json",
        tmp_path / "another" / ".cursor-plugin" / "plugin.json",
    ):
        manifest.parent.mkdir(parents=True)
        manifest.write_text('{"name": "x"}', encoding="utf-8")
        place = (
            manifest.parent
            if manifest.name == "plugin.json" and manifest.parent.name in {"rooted"}
            else manifest.parent.parent
        )
        report = skill_package.validate(place)
        assert report.packaged_as == "plugin", place
        assert report.conforms
        assert report.findings == ()


def test_our_own_extra_directories_do_not_make_a_package_non_conforming(
    tmp_path: Path,
) -> None:
    """ "A skill directory may contain any files and directories beyond SKILL.md."

    So `evals/` and `tests/` cannot be a deviation. They are reported apart from
    the standard's own conventions so a reader can tell which is which.
    """
    place = _package(tmp_path, "with-evals")
    (place / "evals").mkdir()
    (place / "tests").mkdir()
    (place / "scripts").mkdir()
    (place / "NOTES.md").write_text("notes\n", encoding="utf-8")
    report = skill_package.validate(place)
    assert report.conforms
    assert report.extension_directories == ("evals", "tests")
    assert report.standard_directories == ("scripts",)
    assert report.other_entries == ("NOTES.md",)


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("# no frontmatter\n", "SK004"),
        ("---\nname: x\n", "SK005"),
        ("---\n\tbad: [\n---\nbody\n", "SK006"),
        ("---\njust a string\n---\nbody\n", "SK007"),
    ],
)
def test_frontmatter_that_cannot_be_read_says_which_way_it_failed(
    tmp_path: Path, text: str, code: str
) -> None:
    place = tmp_path / "broken"
    place.mkdir()
    (place / "SKILL.md").write_text(text, encoding="utf-8")
    assert code in {item.code for item in skill_package.validate(place).findings}


def test_a_path_that_is_not_a_directory_is_refused(tmp_path: Path) -> None:
    plain = tmp_path / "a-file"
    plain.write_text("x\n", encoding="utf-8")
    report = skill_package.validate(plain)
    assert not report.conforms
    assert report.packaged_as == "unknown"
    assert [item.code for item in report.findings] == ["SK001"]


def test_every_skill_text_this_repository_ships_conforms(tmp_path: Path) -> None:
    """The validator applied to our own work, as it is actually delivered.

    Checked in materialised form rather than in the source tree, because the
    source tree is not the package: the texts live under `skills/canonical/` and
    `skills/projections/`, and `skill install` writes them to a destination the
    caller names. Validating them where they are stored would report `SK013`
    for every one — a directory/name mismatch that exists only in the build
    layout and never in anything installed. Excluding that code to make the
    check pass would have been the same as not running it.
    """
    from ai_stp_cli.skill import HARNESSES, available

    texts = {None: available(None), **{harness: available(harness) for harness in HARNESSES}}
    assert len(texts) == len(HARNESSES) + 1

    for label, text in texts.items():
        declared = next(
            (
                line.partition(":")[2].strip()
                for line in text.splitlines()
                if line.startswith("name:")
            ),
            "",
        )
        assert declared, f"{label}: the shipped skill declares no name"
        place = tmp_path / str(label) / declared
        place.mkdir(parents=True)
        (place / "SKILL.md").write_text(text, encoding="utf-8")
        report = skill_package.validate(place)
        assert report.conforms, f"{label}: {[(i.code, i.summary) for i in report.findings]}"
