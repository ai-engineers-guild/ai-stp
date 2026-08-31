from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from docs_scripts.contract_lint import (
    COMPONENT_TYPES,
    MCP_TRANSPORTS,
    SIDECAR_NAMES,
    ContractLinter,
)

GIT_WORKFLOW_DOC = """---
description: "Ветки"
last_verified: "2026-08-04"
---

# Git workflow

`main` — единственная линия репозитория.
"""

WORKFLOW = """name: check

on:
  push:
    branches: [main]
  pull_request:
"""

SERENA_IGNORE = """/cache
/project.local.yml
/.auto_sync_head
/.flow_blocker_ack.json
/.flow_post_task_state.json
/.flow_sync_marker
/.serena_sync_state.json
"""

REPO_STRUCTURE = """---
description: "Структура"
last_verified: "2026-08-04"
---

# Структура репозитория

```text
apps/
docs/
specs/
```
"""


def passports_doc() -> str:
    rows = "\n".join(f"| `{name}` | пример | признак |" for name in COMPONENT_TYPES)
    sidecars = "\n".join(SIDECAR_NAMES)
    return (
        '---\ndescription: "Паспорта"\nlast_verified: "2026-08-05"\n---\n\n'
        "# Паспорта\n\n```text\n" + sidecars + "\n```\n\n"
        "| Вид | Пример | Признак |\n|---|---|---|\n" + rows + "\n"
    )


def validation_policy() -> str:
    rows = "\n".join(f"| `{name}` | обязательные проверки |" for name in COMPONENT_TYPES)
    transports = "\n".join(f"| `{name}` | обязательные проверки |" for name in MCP_TRANSPORTS)
    return (
        '---\ndescription: "Политика"\nlast_verified: "2026-08-04"\n---\n\n'
        "# Политика проверок\n\n"
        "| Вид | Проверки |\n|---|---|\n" + rows + "\n\n"
        "| Класс | Проверки |\n|---|---|\n" + transports + "\n\n"
        "## Installation eligibility\n\n"
        "A version without current evidence is blocked for new installations and updates.\n\n"
        "## Author attestation\n\n"
        "Запись привязана к точному хэшу и версии политики.\n"
    )


VISION_CONTRACT_FIXTURES = {
    "docs/contracts/device-passport.md": "Full device passports are not merged.",
    "docs/contracts/unverified-consent.md": (
        "Области `publisher` и `object_major` выбирает пользователь."
    ),
    "docs/contracts/access-grants-and-forks.md": (
        "An unchanged clone is not published under a new name."
    ),
    "docs/contracts/report-case.md": "A public issue is not created automatically from a report.",
    "docs/contracts/selection-proposal.md": "Confirmation is atomic.",
}


class ContractLintTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.write("docs/engineering/git-workflow.md", GIT_WORKFLOW_DOC)
        self.write("docs/engineering/repository-structure.md", REPO_STRUCTURE)
        self.write("docs/contracts/validation-policy.md", validation_policy())
        self.write("docs/contracts/component-setup-passports.md", passports_doc())
        self.write(".github/workflows/check.yml", WORKFLOW)
        self.write(".serena/.gitignore", SERENA_IGNORE)
        for relative, marker in VISION_CONTRACT_FIXTURES.items():
            self.write(relative, self.doc(marker))
        self.write(
            "specs/active/SPEC-016-reports-moderation.md",
            self.doc("Жалобы создают закрытый случай модерации."),
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def codes(self) -> set[str]:
        linter = ContractLinter(self.root)
        linter.run()
        return {issue.code for issue in linter.issues}

    def doc(self, body: str) -> str:
        return (
            '---\ndescription: "Проверка"\nlast_verified: "2026-08-04"\n---'
            f"\n\n# Документ\n\n{body}\n"
        )

    # -- базовое состояние ----------------------------------------------

    def test_clean_tree_passes(self) -> None:
        self.assertEqual(self.codes(), set())

    # -- отменённые термины ---------------------------------------------

    def test_manifest_digest_fails(self) -> None:
        self.write("docs/contracts/x.md", self.doc("Ссылка содержит `manifest_digest` версии."))
        self.assertIn("CT001", self.codes())

    def test_manifest_hash_domain_fails(self) -> None:
        self.write(
            "docs/contracts/x.md", self.doc("Область ai-stp:manifest:v1 применяется к версии.")
        )
        self.assertIn("CT002", self.codes())

    def test_setup_variant_entity_fails(self) -> None:
        self.write(
            "docs/contracts/x.md", self.doc("Каждый `SetupVariant` имеет собственные версии.")
        )
        self.assertIn("CT003", self.codes())

    def test_inferred_origin_fails(self) -> None:
        self.write(
            "docs/contracts/x.md", self.doc("Происхождение `inferred` допускается для оценки.")
        )
        self.assertIn("CT004", self.codes())

    def test_setup_level_variant_id_fails(self) -> None:
        self.write("docs/contracts/x.md", self.doc("Паспорт версии сетапа содержит `variant_id`."))
        self.assertIn("CT005", self.codes())

    def test_marketplace_as_component_type_fails(self) -> None:
        self.write(
            "specs/active/x.md", self.doc("`component_type` принимает значение `marketplace`.")
        )
        self.assertIn("CT006", self.codes())

    def test_operation_succeeded_fails(self) -> None:
        self.write(
            "specs/active/x.md", self.doc("Операция имеет состояние `succeeded` при успехе.")
        )
        self.assertIn("CT007", self.codes())

    def test_fit_terminology_fails(self) -> None:
        self.write("specs/active/x.md", self.doc("`FitRun` проходит состояния подбора."))
        self.assertIn("CT008", self.codes())

    def test_unsupported_apply_as_state_fails(self) -> None:
        self.write(
            "specs/active/x.md", self.doc("Контур возвращает состояние `unsupported_apply` здесь.")
        )
        self.assertIn("CT009", self.codes())

    # -- формулировка запрета не является нарушением ---------------------

    def test_prohibition_wording_passes(self) -> None:
        self.write(
            "docs/contracts/x.md",
            self.doc(
                "Поля `variant_id` у сетапа нет.\n\n"
                "Отдельной сущности `SetupVariant` не существует.\n\n"
                "Происхождение `inferred` не используется.\n\n"
                "`marketplace` не является видом компонента.\n\n"
                "У операции нет состояния `succeeded`: успех называется `verified`."
            ),
        )
        self.assertEqual(self.codes(), set())

    def test_component_level_variant_id_passes(self) -> None:
        self.write(
            "docs/contracts/x.md",
            self.doc("Ссылка на версию компонента содержит необязательный `variant_id`."),
        )
        self.assertEqual(self.codes(), set())

    def test_english_prohibition_wording_passes(self) -> None:
        self.write(
            "docs/contracts/x.md",
            self.doc(
                "A setup has no `variant_id`.\n\n"
                "The `inferred` origin is not used.\n\n"
                "The `search.include_unverified` key has been removed."
            ),
        )
        self.assertEqual(self.codes(), set())

    def test_adr_history_is_exempt(self) -> None:
        self.write(
            "docs/adr/ADR-0099-history.md",
            self.doc("Прежняя модель использовала `manifest_digest` и `SetupVariant`."),
        )
        self.assertEqual(self.codes(), set())

    # -- ветки ------------------------------------------------------------

    def test_workflow_branch_mismatch_fails(self) -> None:
        self.write(".github/workflows/check.yml", WORKFLOW.replace("[main]", "[main, rldyourmnd]"))
        self.assertIn("CT013", self.codes())

    def test_workflow_missing_declared_line_fails(self) -> None:
        self.write(
            "docs/engineering/git-workflow.md",
            GIT_WORKFLOW_DOC.replace("`main` — единственная линия репозитория.", "Ветки бывают."),
        )
        self.assertIn("CT012", self.codes())

    # -- матрица проверок --------------------------------------------------

    def test_missing_component_type_row_fails(self) -> None:
        self.write(
            "docs/contracts/validation-policy.md",
            validation_policy().replace("| `hook` | обязательные проверки |\n", ""),
        )
        self.assertIn("CT021", self.codes())

    def test_missing_mcp_transport_row_fails(self) -> None:
        self.write(
            "docs/contracts/validation-policy.md",
            validation_policy().replace("| `remote_https` | обязательные проверки |\n", ""),
        )
        self.assertIn("CT022", self.codes())

    # -- примеры и имена файлов --------------------------------------------

    def test_missing_component_type_example_fails(self) -> None:
        self.write(
            "docs/contracts/component-setup-passports.md",
            passports_doc().replace("| `plugin` | пример | признак |\n", ""),
        )
        self.assertIn("CT024", self.codes())

    def test_missing_sidecar_name_fails(self) -> None:
        self.write(
            "docs/contracts/component-setup-passports.md",
            passports_doc().replace("ai-stp.setup.yaml\n", ""),
        )
        self.assertIn("CT025", self.codes())

    # -- состояние сессии --------------------------------------------------

    def test_missing_runtime_ignore_entry_fails(self) -> None:
        self.write(".serena/.gitignore", "/cache\n/project.local.yml\n")
        self.assertIn("CT032", self.codes())

    # -- удалённый каталог работ -------------------------------------------

    def test_work_directory_in_structure_fails(self) -> None:
        self.write(
            "docs/engineering/repository-structure.md",
            REPO_STRUCTURE.replace("specs/\n", "specs/\n.work/\n"),
        )
        self.assertIn("CT040", self.codes())

    # -- возвраты закрытых решений видения ---------------------------------

    def test_include_unverified_fails(self) -> None:
        self.write("docs/contracts/x.md", self.doc("Ключ `include_unverified` включает всё сразу."))
        self.assertIn("CT050", self.codes())

    def test_include_unverified_removal_wording_passes(self) -> None:
        self.write(
            "docs/contracts/x.md", self.doc("Ключ `search.include_unverified` удалён навсегда.")
        )
        self.assertNotIn("CT050", self.codes())

    def test_permanent_ceiling_fails(self) -> None:
        self.write(
            "docs/product/x.md",
            self.doc("Пять — целевое число продукта, список не планируется расширять."),
        )
        self.assertIn("CT051", self.codes())

    def test_publishable_not_run_fails(self) -> None:
        self.write(
            "docs/contracts/x.md",
            self.doc(
                "Проверка возвращает `not_run` с причиной, и такая версия публикуется без бейджа."
            ),
        )
        self.assertIn("CT052", self.codes())

    def test_blocking_not_run_passes(self) -> None:
        self.write(
            "docs/contracts/x.md",
            self.doc(
                "Обязательная проверка `not_run` блокирует публичную публикацию, "
                "а `warning` публикацию не блокирует."
            ),
        )
        self.assertNotIn("CT052", self.codes())

    def test_web_only_scope_fails(self) -> None:
        self.write(
            "docs/product/x.md",
            self.doc("Сайт в MVP нужен только для установки, входа и публичного поиска."),
        )
        self.assertIn("CT053", self.codes())

    def test_hardcoded_counts_fail(self) -> None:
        self.write(
            "docs/engineering/x.md",
            self.doc("Приняты 13 ADR и 15 активных спецификаций со 147 требованиями."),
        )
        self.assertIn("CT054", self.codes())

    def test_developer_passport_env_fails(self) -> None:
        self.write(
            "specs/active/x.md",
            self.doc("Паспорт разработчика хранит OS, архитектуру и версии инструментов."),
        )
        self.assertIn("CT055", self.codes())

    def test_device_ownership_wording_passes(self) -> None:
        self.write(
            "specs/active/x.md",
            self.doc(
                "Наблюдаемые OS и архитектура принадлежат ему, а не паспорту разработчика.\n\n"
                "Паспорт разработчика не содержит наблюдаемую архитектуру."
            ),
        )
        self.assertNotIn("CT055", self.codes())

    def test_an_unrelated_negation_does_not_exempt_the_violation(self) -> None:
        """The planted control the old four-phrase skip let through.

        A real violation — the developer passport carrying OS and architecture —
        with `не изменяет` in a clause about something else entirely. The
        exemption is for a negation that binds to the passport; a negation
        anywhere on the line is not the same claim, and reading it as one is how
        a check keeps its green while admitting what it was written to catch.
        """
        self.write(
            "specs/active/x.md",
            self.doc(
                "Паспорт разработчика несёт операционную систему и архитектуру "
                "машины, и порядок записей не изменяет их смысл."
            ),
        )
        self.assertIn("CT055", self.codes())

    def test_the_wording_the_estate_actually_uses_is_exempt(self) -> None:
        """`ADR-0025` phrases it this way, and the old skip did not carry it."""
        self.write(
            "specs/active/x.md",
            self.doc(
                "Наблюдаемые операционная система, архитектура и версии "
                "инструментов не входят в паспорт разработчика."
            ),
        )
        self.assertNotIn("CT055", self.codes())

    def test_report_channel_excluded_fails(self) -> None:
        self.write("specs/active/x.md", self.doc("Пользовательского канала жалоб в MVP нет."))
        self.assertIn("CT056", self.codes())

    def test_platform_only_validation_fails(self) -> None:
        self.write(
            "docs/contracts/x.md",
            self.doc("Полный набор обязательных проверок запускается на сервере платформы."),
        )
        self.assertIn("CT064", self.codes())

    def test_missing_vision_contract_fails(self) -> None:
        (self.root / "docs/contracts/report-case.md").unlink()
        self.assertIn("CT062", self.codes())

    def test_missing_vision_marker_fails(self) -> None:
        self.write(
            "docs/contracts/unverified-consent.md", self.doc("Записи согласия без областей.")
        )
        self.assertIn("CT063", self.codes())

    def test_missing_reports_spec_fails(self) -> None:
        (self.root / "specs/active/SPEC-016-reports-moderation.md").unlink()
        self.assertIn("CT065", self.codes())

    def test_missing_eligibility_marker_fails(self) -> None:
        self.write(
            "docs/contracts/validation-policy.md",
            validation_policy()
            .replace("## Installation eligibility\n\n", "")
            .replace(
                "A version without current evidence is blocked "
                "for new installations and updates.\n\n",
                "",
            ),
        )
        self.assertIn("CT060", self.codes())

    def test_missing_attestation_marker_fails(self) -> None:
        self.write(
            "docs/contracts/validation-policy.md",
            validation_policy().replace("## Author attestation", "## Other"),
        )
        self.assertIn("CT061", self.codes())

    def test_bare_object_id_fails(self) -> None:
        self.write(
            "docs/contracts/x.md", self.doc("```yaml\nid: component_01J0000000000000000000\n```")
        )
        self.assertIn("CT066", self.codes())

    def test_stable_id_passes(self) -> None:
        self.write(
            "docs/contracts/x.md",
            self.doc("```yaml\nstable_id: component_01J0000000000000000000\n```"),
        )
        self.assertNotIn("CT066", self.codes())


if __name__ == "__main__":
    unittest.main()
