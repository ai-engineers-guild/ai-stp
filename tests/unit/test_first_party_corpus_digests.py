"""The corpus digest gate names member drift, missing members and strays."""

from pathlib import Path

from release_scripts import first_party_corpus_digests


def _corpus(tmp_path: Path) -> Path:
    (tmp_path / "a-component.json").write_text('{"a": 1}\n', encoding="utf-8")
    (tmp_path / "corpus-sources.json").write_text('{"sources": []}\n', encoding="utf-8")
    (tmp_path / "SHA256SUMS").write_text(
        first_party_corpus_digests.render(tmp_path), encoding="utf-8"
    )
    return tmp_path


def test_the_exact_committed_set_passes(tmp_path: Path) -> None:
    assert first_party_corpus_digests.check(_corpus(tmp_path)) == []


def test_a_drifted_member_is_named(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    (corpus / "a-component.json").write_text('{"a": 2}\n', encoding="utf-8")

    assert any(
        "a-component.json" in problem for problem in first_party_corpus_digests.check(corpus)
    )


def test_a_missing_member_is_named(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    (corpus / "corpus-sources.json").unlink()

    assert any(
        "corpus-sources.json" in problem for problem in first_party_corpus_digests.check(corpus)
    )


def test_an_unlisted_file_is_named(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    (corpus / "stray.json").write_text("{}\n", encoding="utf-8")

    assert any("stray.json" in problem for problem in first_party_corpus_digests.check(corpus))
