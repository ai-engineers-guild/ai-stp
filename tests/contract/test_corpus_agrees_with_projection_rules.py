"""The corpus and the projection table must say one thing about where a kind goes.

`composition.PROVIDER_RULES` decides where a component of one kind projects for
one harness. `first_party._native_path` decided it a second time, for the same
kinds and the same harnesses, in another package — and nothing compared them.

They had drifted in four places by the time anything asked, and the drift was
already published:

- 61 codex skills at `.agents/skills/<slug>`, relative to `$HOME`, from before
  the surface became its own scope with `~/.agents` as its target;
- one cursor plugin at `plugins/<slug>` where the product reads `plugins/local`;
- one cursor `instruction`, for a global `~/.cursor/AGENTS.md` that does not
  exist — the released provider had already stopped declaring the kind;
- one antigravity plugin where the **rule** was wrong and the corpus was right:
  it said `antigravity-cli/plugins`, the directory the CLI manages itself, and
  the product ships its own plugin at `config/plugins`.

That last one is why this is a comparison and not a derivation. Neither side is
authoritative by construction — the corpus is what a real setup repository
actually ships, and the table is what this compiler will write. When they
disagree, somebody has to go and look at the product. What must never happen
again is disagreeing without anybody noticing.

`ADR-0127` scopes make the comparison legal to state at all: a rule naming
`skills` means `<config home>/skills` under `global` and `~/.agents/skills`
under `user_root`, so the root has to be named before two paths are comparable.
"""

from __future__ import annotations

from ai_stp_cli.local import composition
from ai_stp_contracts.first_party import versions
from ai_stp_passports.versions import ComponentVersionPassport


def test_every_corpus_component_projects_where_its_rule_says() -> None:
    disagreements: list[str] = []
    unruled: list[str] = []
    for item in versions():
        passport = item.passport
        # `isinstance`, not `item.kind`: the kind string is right but does not
        # narrow the union, and reading a component field off the setup half is
        # exactly the mistake this file exists to catch elsewhere.
        if not isinstance(passport, ComponentVersionPassport):
            continue
        for adaptation in passport.adaptations:
            for scope in adaptation.scope_adaptations:
                rule = composition.rule_for(
                    passport.component_type, adaptation.harness_id, scope=scope.scope
                )
                if rule is None:
                    unruled.append(
                        f"{adaptation.harness_id}/{scope.scope}/{passport.component_type}"
                    )
                    continue
                for member in scope.members:
                    path = member.path
                    if path != rule.relative and not path.startswith(f"{rule.relative}/"):
                        disagreements.append(
                            f"{adaptation.harness_id}/{scope.scope}/{passport.component_type}: "
                            f"corpus says {path!r}, rule says {rule.relative!r}"
                        )
    assert not unruled, sorted(set(unruled))
    assert not disagreements, sorted(set(disagreements))


def test_the_corpus_covers_every_harness_the_table_projects_for() -> None:
    """A rule nothing publishes against is a rule nothing checks.

    Not a demand that every kind be published — most are not. It is the weaker
    and checkable claim that each harness with rules has some corpus object, so
    the comparison above has something to compare for all of them.
    """
    ruled = {rule.harness_id for rule in composition.PROVIDER_RULES}
    published = {
        adaptation.harness_id
        for item in versions()
        if isinstance(item.passport, ComponentVersionPassport)
        for adaptation in item.passport.adaptations
    }
    assert ruled <= published, sorted(ruled - published)
