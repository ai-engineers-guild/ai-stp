#!/usr/bin/env python3
"""Семантические регрессии: отменённые термины, ветки и покрытие политики проверок.

Запускается через just, а не напрямую:

    just docs-static

Обычный docs_lint проверяет форму документа. Здесь проверяется смысл: что решение,
уже принятое в ADR, не вернулось в нормативный текст другим словом. Такая ошибка не
ломает ссылки и не видна разметке, поэтому её ловит отдельный проход.

Историю в docs/adr/ проверки терминов не трогают: заменённое решение обязано уметь
описать, что именно оно заменило.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Нормативные корни. docs/adr описывает историю решений и здесь не участвует.
NORMATIVE_GLOBS = ("docs/**/*.md", "specs/**/*.md")
HISTORY_DIR = "docs/adr"
ROOT_DOCS = ("README.md", "AGENTS.md", "QUICKSTART.md", "SECURITY.md", "CONTRIBUTING.md")

# Восемь видов компонентов по ADR-0015. Каждый обязан иметь строку в матрице.
COMPONENT_TYPES = (
    "instruction",
    "skill",
    "mcp",
    "hook",
    "command",
    "agent",
    "plugin",
    "setting",
)

# Классы транспорта MCP по validation-policy.md.
MCP_TRANSPORTS = ("local_exec", "package", "remote_https")

VALIDATION_POLICY = Path("docs/contracts/validation-policy.md")
PASSPORTS_DOC = Path("docs/contracts/component-setup-passports.md")

# Канонические имена файлов-спутников: по ним CLI отличает описанный объект.
SIDECAR_NAMES = ("ai-stp.component.yaml", "ai-stp.setup.yaml")
WORKFLOW = Path(".github/workflows/check.yml")
GIT_WORKFLOW_DOC = Path("docs/engineering/git-workflow.md")
REPO_STRUCTURE_DOC = Path("docs/engineering/repository-structure.md")
SERENA_IGNORE = Path(".serena/.gitignore")

# Файлы состояния конкретного checkout: содержат SHA, ветку и абсолютный путь.
SERENA_TRANSIENT = (
    ".serena/.auto_sync_head",
    ".serena/.flow_blocker_ack.json",
    ".serena/.flow_post_task_state.json",
    ".serena/.flow_sync_marker",
    ".serena/.serena_sync_state.json",
)


@dataclass(frozen=True)
class BannedTerm:
    pattern: str
    code: str
    reason: str


BANNED_TERMS = (
    BannedTerm(
        r"\binclude_unverified\b",
        "CT050",
        "бессрочное глобальное согласие удалено: сеансовый признак и записи областей (ADR-0029)",
    ),
    BannedTerm(
        r"\bmanifest_digest\b",
        "CT001",
        "версия описывается паспортом: используйте passport_digest (ADR-0012, ADR-0014)",
    ),
    BannedTerm(
        r"ai-stp:manifest:v1",
        "CT002",
        "области манифеста версии не существует: используйте ai-stp:passport:v1 (ADR-0014)",
    ),
    BannedTerm(
        r"\bSetupVariant\b",
        "CT003",
        "сетап принадлежит одному харнессу, отдельной сущности варианта нет (ADR-0014)",
    ),
    BannedTerm(
        r"\binferred\b",
        "CT004",
        "происхождение inferred удалено: используйте derived с записанным правилом (ADR-0021)",
    ),
    BannedTerm(
        r"\bFitRun\b|\bno_verified_candidate\b",
        "CT008",
        "продукт ищет и собирает, а не подбирает: SelectionRun и no_candidate",
    ),
    BannedTerm(
        r"`unsupported_apply`",
        "CT009",
        "неподдерживаемое применение является кодом ошибки, а не состоянием оси готовности",
    ),
)

# `variant_id` допустим у компонента и запрещён у сетапа. Ловим только явную связку.
SETUP_VARIANT_RE = re.compile(
    r"(?:сетап[а-яё]*|setup)[^.\n]{0,60}`variant_id`|`variant_id`[^.\n]{0,60}(?:сетап[а-яё]*|setup)",
    re.IGNORECASE,
)

# `marketplace` как вид компонента. Само слово законно: это projection_kind и
# нативная витрина харнесса, поэтому проверяется только перечисление видов.
MARKETPLACE_AS_TYPE_RE = re.compile(
    r"component_type[^.\n]{0,120}\bmarketplace\b"
    r"|\bmarketplace\b[^.\n]{0,80}(?:вид[а-яё]* компонент|component_type)",
    re.IGNORECASE,
)

# `succeeded` как успех изменяющей операции. У задания worker своё состояние.
OPERATION_SUCCEEDED_RE = re.compile(
    r"(?:операц[а-яё]+|operation)[^.\n]{0,160}`succeeded`",
    re.IGNORECASE,
)

# Возвраты закрытых решений видения (ADR-0025..0034). Эти проверки идут в обход
# NEGATION_RE: часть запрещённых формулировок сама записана отрицанием
# («не планируется расширять», «канала жалоб нет»), и общая льгота их спрятала бы.
CEILING_RE = re.compile(r"целевое число продукта|не планируется расширять")
WEB_ONLY_RE = re.compile(
    r"(?:[Сс]айт|[Вв]еб)[^\n]{0,60}?только для[^\n]{0,60}?(?:установк|вход|поиск)",
)
COUNTS_RE = re.compile(
    r"\b\d{1,4} ADR\b|\b\d{1,4} активн[а-яё]+ спецификаци"
    r"|\bсо \d{1,4} требовани|\b\d{1,4} требовани[а-яё]*\b",
)
#: A claim about which phase is finished or starting. `implementation-roadmap.md`
#: owns that fact; anywhere else it is a copy that goes stale on the next phase.
#: It did: `scope.md` said phase 1 was beginning while the roadmap had it done.
PHASE_STATE_RE = re.compile(
    r"[Фф]аза \d+[^\n]{0,40}(завершена|начина)|(начинается|завершена) фаза \d+"
)

NOT_RUN_PUBLISH_RE = re.compile(r"не блокиру|публикуется")
NOT_RUN_BLOCKING_RE = re.compile(r"блокиру[а-яё]*[^\n]{0,20}публ")
DEV_PASSPORT_RE = re.compile(r"паспорт[а-яё]* разработчика|DeveloperPassport", re.IGNORECASE)
ENV_FACT_RE = re.compile(
    r"\bOS\b|\barchitecture\b|операционн[а-яё]+ систем|архитектур"
    r"|установленн[а-яё]+ харнесс|верси[а-яё]+ инструмент",
)
DEV_PASSPORT_SKIP_RE = re.compile(
    r"не содержит|а не паспорту разработчика|не записывается|не изменяет",
)
REPORT_EXCLUDED_RE = re.compile(
    r"канал[а-яё]* жалоб[^\n]{0,30}нет|пользовательск[а-яё]+ жалоб[а-яё]* на компонент",
)
PLATFORM_ONLY_RE = re.compile(
    r"полн[а-яё]+ набор обязательных проверок[^\n]{0,60}"
    r"(?:выполняется|запускается)[^\n]{0,40}на сервере",
    re.IGNORECASE,
)
BARE_ID_RE = re.compile(
    r"^\s*(?:\"id\"|id):\s*\"?(?:component_|setup_|developer_|device_|project_)",
)

# Канонические владельцы закрытых решений: файл и маркеры, без которых решение
# считается потерянным. Удаление владельца или маркера — регрессия, а не чистка.
VISION_CONTRACTS = {
    Path("docs/contracts/device-passport.md"): ("не объединяются",),
    Path("docs/contracts/unverified-consent.md"): ("`publisher`", "`object_major`"),
    Path("docs/contracts/access-grants-and-forks.md"): ("Неизменённый клон",),
    Path("docs/contracts/report-case.md"): ("не создаётся автоматически",),
    Path("docs/contracts/selection-proposal.md"): ("атомарно",),
}
REPORTS_SPEC = Path("specs/active/SPEC-016-reports-moderation.md")
ELIGIBILITY_MARKERS = ("Пригодность к установке", "блокируется для новых установок и обновлений")
ATTESTATION_MARKER = "Авторское подтверждение"


# Канонический документ обязан уметь назвать отменённый термин, чтобы его запретить.
# Строка с отрицанием — это формулировка правила, а не его нарушение. Возврат термина
# так не выглядит: его вводят утвердительно, как поле или допустимое значение.
NEGATION_RE = re.compile(
    r"\bне\s+(?:использ|являет|существу|содерж|входит|добавля|планиру|принима|создаёт|получа)"
    r"|\bнет\b|\bбез\b|\bудал[её]н|\bудаляет|\bзапрещ|\bперестал|\bотменён|\bне\s+нужн"
    r"|\bвместо\b|\bзаменён|\bсокращён",
    re.IGNORECASE,
)


@dataclass
class Issue:
    path: str
    code: str
    message: str


class ContractLinter:
    def __init__(self, root: Path = ROOT) -> None:
        self.root = root
        self.issues: list[Issue] = []

    def error(self, path: Path | str, code: str, message: str) -> None:
        self.issues.append(Issue(str(path), code, message))

    def normative_files(self) -> list[Path]:
        files: list[Path] = []
        for name in ROOT_DOCS:
            candidate = self.root / name
            if candidate.exists():
                files.append(candidate)
        for pattern in NORMATIVE_GLOBS:
            for path in sorted(self.root.glob(pattern)):
                rel = path.relative_to(self.root).as_posix()
                if rel.startswith(f"{HISTORY_DIR}/"):
                    continue
                files.append(path)
        return files

    def run(self) -> None:
        self.check_banned_terms()
        self.check_branch_parity()
        self.check_validation_matrix()
        self.check_component_type_examples()
        self.check_sidecar_names()
        self.check_tracked_runtime_state()
        self.check_removed_work_dir()
        self.check_vision_regressions()
        self.check_vision_owners()

    # -- проверки --------------------------------------------------------

    def check_banned_terms(self) -> None:
        contextual = (
            (
                SETUP_VARIANT_RE,
                "CT005",
                "variant_id уровня сетапа удалён; вариант остаётся только у компонента (ADR-0014)",
            ),
            (
                MARKETPLACE_AS_TYPE_RE,
                "CT006",
                "marketplace не является видом компонента: это projection_kind (ADR-0015)",
            ),
            (
                OPERATION_SUCCEEDED_RE,
                "CT007",
                "единственное имя успеха операции — verified (contracts/operation.md)",
            ),
        )
        for path in self.normative_files():
            rel = path.relative_to(self.root).as_posix()
            seen: set[str] = set()
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if NEGATION_RE.search(line):
                    continue
                for term in BANNED_TERMS:
                    if term.code not in seen and re.search(term.pattern, line):
                        seen.add(term.code)
                        self.error(f"{rel}:{number}", term.code, term.reason)
                for pattern, code, reason in contextual:
                    if code not in seen and pattern.search(line):
                        seen.add(code)
                        self.error(f"{rel}:{number}", code, reason)

    def check_branch_parity(self) -> None:
        """Ветки push в workflow обязаны совпадать с документированными."""
        workflow = self.root / WORKFLOW
        doc = self.root / GIT_WORKFLOW_DOC
        if not workflow.exists() or not doc.exists():
            self.error(WORKFLOW, "CT010", "нет workflow или документа о ветках")
            return

        match = re.search(
            r"push:\s*\n\s*branches:\s*\[([^\]]*)\]", workflow.read_text(encoding="utf-8")
        )
        if not match:
            self.error(WORKFLOW, "CT011", "не найден список branches у push")
            return
        actual = {item.strip().strip("\"'") for item in match.group(1).split(",") if item.strip()}

        text = doc.read_text(encoding="utf-8")
        # Одна линия, а не пара «интеграционная плюс выпускная»: второй ветки
        # больше нет, и раньше правило требовало ровно её. Сторож остаётся, но
        # читает объявленную линию, а не предполагает её имя: расхождение
        # workflow с документом должно падать здесь, а не обнаруживаться тем,
        # что проверки перестали запускаться на ветке, куда идут PR.
        declared = re.search(r"`(\w[\w./-]*)` — единственная линия репозитория", text)
        if not declared:
            self.error(GIT_WORKFLOW_DOC, "CT012", "документ не называет единственную линию")
            return
        expected = {declared.group(1)}

        if actual != expected:
            self.error(
                WORKFLOW,
                "CT013",
                f"push ветки {sorted(actual)} расходятся с документированными {sorted(expected)}",
            )

    def check_validation_matrix(self) -> None:
        """Каждый вид компонента и класс транспорта MCP имеет строку матрицы."""
        policy = self.root / VALIDATION_POLICY
        if not policy.exists():
            self.error(VALIDATION_POLICY, "CT020", "нет канонической матрицы политики проверок")
            return
        text = policy.read_text(encoding="utf-8")
        for component_type in COMPONENT_TYPES:
            if not re.search(rf"\|\s*`{re.escape(component_type)}`\s*\|", text):
                self.error(
                    VALIDATION_POLICY,
                    "CT021",
                    f"нет строки матрицы для вида компонента `{component_type}`",
                )
        for transport in MCP_TRANSPORTS:
            if not re.search(rf"\|\s*`{re.escape(transport)}`\s*\|", text):
                self.error(
                    VALIDATION_POLICY,
                    "CT022",
                    f"нет строки матрицы для класса транспорта `{transport}`",
                )

    def check_component_type_examples(self) -> None:
        """У каждого вида компонента есть пример правила отнесения."""
        doc = self.root / PASSPORTS_DOC
        if not doc.exists():
            self.error(PASSPORTS_DOC, "CT023", "нет контракта паспортов компонентов и сетапов")
            return
        text = doc.read_text(encoding="utf-8")
        for component_type in COMPONENT_TYPES:
            if not re.search(rf"\|\s*`{re.escape(component_type)}`\s*\|[^|\n]+\|", text):
                self.error(
                    PASSPORTS_DOC,
                    "CT024",
                    f"нет примера отнесения для вида `{component_type}`",
                )

    def check_sidecar_names(self) -> None:
        """Имя файла-спутника является машинной границей и объявлено явно."""
        doc = self.root / PASSPORTS_DOC
        if not doc.exists():
            return
        text = doc.read_text(encoding="utf-8")
        for name in SIDECAR_NAMES:
            if name not in text:
                self.error(
                    PASSPORTS_DOC,
                    "CT025",
                    f"не объявлено каноническое имя файла-спутника {name}",
                )

    def check_tracked_runtime_state(self) -> None:
        """Состояние конкретного checkout не отслеживается и объявлено в ignore.

        Обе половины независимы: объявление в ignore проверяется и там, где Git
        недоступен, иначе проверка молча исчезает вместе с рабочим деревом.
        """
        try:
            tracked = subprocess.run(
                ["git", "ls-files", "-z", "--", ".serena"],
                cwd=self.root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.split("\0")
        except (OSError, subprocess.CalledProcessError):
            tracked = []  # Вне рабочего дерева Git отслеживание проверить нечем.

        tracked_set = {item for item in tracked if item}
        for name in SERENA_TRANSIENT:
            if name in tracked_set:
                self.error(
                    name,
                    "CT030",
                    "состояние конкретного checkout снова отслеживается: SHA, ветка и путь машины",
                )

        ignore = self.root / SERENA_IGNORE
        if not ignore.exists():
            self.error(SERENA_IGNORE, "CT031", "нет файла ignore для состояния сессии")
            return
        declared = {
            line.strip().lstrip("/") for line in ignore.read_text(encoding="utf-8").splitlines()
        }
        for name in SERENA_TRANSIENT:
            basename = Path(name).name
            if basename not in declared:
                self.error(SERENA_IGNORE, "CT032", f"в ignore не объявлен {basename}")

    def check_removed_work_dir(self) -> None:
        """Удалённый каталог работ не возвращается через документацию структуры."""
        doc = self.root / REPO_STRUCTURE_DOC
        if not doc.exists():
            return
        for number, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"^\s*\.work/\s*$", line):
                self.error(
                    f"{REPO_STRUCTURE_DOC}:{number}",
                    "CT040",
                    "каталог .work удалён вместе с валидатором и не входит в целевую структуру",
                )

    def check_vision_regressions(self) -> None:
        """Закрытые решения видения не возвращаются другим словом.

        Проверки идут в обход NEGATION_RE: часть запрещённых формулировок сама
        записана отрицанием, и общая льгота формулировок-запретов их скрыла бы.
        """
        rules = (
            (
                "CT051",
                CEILING_RE,
                None,
                "пять харнессов — полный набор MVP, продвижение по ADR-0033; "
                "вечный потолок отменён",
            ),
            (
                "CT053",
                WEB_ONLY_RE,
                None,
                "веб владеет учётной записью и каталогом по ADR-0018, "
                "а не только установкой и поиском",
            ),
            (
                "CT054",
                COUNTS_RE,
                None,
                "числа решений и требований живут в генерируемых индексах, а не в прозе",
            ),
            (
                "CT056",
                REPORT_EXCLUDED_RE,
                None,
                "жалобы входят в MVP: закрытый ReportCase по SPEC-016 (ADR-0031)",
            ),
            (
                "CT064",
                PLATFORM_ONLY_RE,
                None,
                "принятый источник задаётся по каждой проверке: credential-зависимые "
                "принимаются авторским подтверждением (ADR-0026)",
            ),
            (
                "CT066",
                BARE_ID_RE,
                None,
                "идентичность объекта называется stable_id, а не id (SPEC-015 REQ-1501)",
            ),
        )
        for path in self.normative_files():
            rel = path.relative_to(self.root).as_posix()
            seen: set[str] = set()
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for code, pattern, skip, reason in rules:
                    if code in seen or not pattern.search(line):
                        continue
                    if skip and skip.search(line):
                        continue
                    seen.add(code)
                    self.error(f"{rel}:{number}", code, reason)
                if (
                    "CT057" not in seen
                    and rel != "docs/engineering/implementation-roadmap.md"
                    and PHASE_STATE_RE.search(line)
                ):
                    seen.add("CT057")
                    self.error(
                        f"{rel}:{number}",
                        "CT057",
                        "состояние фазы принадлежит implementation-roadmap.md, "
                        "а копия расходится с ним на следующей же фазе",
                    )
                if (
                    "CT052" not in seen
                    and "`not_run`" in line
                    and NOT_RUN_PUBLISH_RE.search(line)
                    and not NOT_RUN_BLOCKING_RE.search(line)
                ):
                    seen.add("CT052")
                    self.error(
                        f"{rel}:{number}",
                        "CT052",
                        "обязательный not_run блокирует публикацию; "
                        "публикуемый not_run отменён (ADR-0026)",
                    )
                if (
                    "CT055" not in seen
                    and DEV_PASSPORT_RE.search(line)
                    and ENV_FACT_RE.search(line)
                    and not DEV_PASSPORT_SKIP_RE.search(line)
                ):
                    seen.add("CT055")
                    self.error(
                        f"{rel}:{number}",
                        "CT055",
                        "наблюдаемое окружение принадлежит паспорту устройства, "
                        "а не разработчика (ADR-0025)",
                    )

    def check_vision_owners(self) -> None:
        """Канонические владельцы закрытых решений существуют и несут маркеры."""
        for relative, markers in VISION_CONTRACTS.items():
            path = self.root / relative
            if not path.exists():
                self.error(relative, "CT062", "нет канонического контракта закрытого решения")
                continue
            text = path.read_text(encoding="utf-8")
            for marker in markers:
                if marker not in text:
                    self.error(
                        relative,
                        "CT063",
                        f"в контракте нет обязательного маркера решения: {marker}",
                    )
        if not (self.root / REPORTS_SPEC).exists():
            self.error(REPORTS_SPEC, "CT065", "нет спецификации жалоб и модерации")
        policy = self.root / VALIDATION_POLICY
        if policy.exists():
            text = policy.read_text(encoding="utf-8")
            for marker in ELIGIBILITY_MARKERS:
                if marker not in text:
                    self.error(
                        VALIDATION_POLICY,
                        "CT060",
                        f"в политике проверок нет маркера пригодности: {marker}",
                    )
            if ATTESTATION_MARKER not in text:
                self.error(
                    VALIDATION_POLICY,
                    "CT061",
                    "в политике проверок нет раздела авторского подтверждения",
                )

    # -- вывод -----------------------------------------------------------

    def report(self, fmt: str) -> int:
        if fmt == "github":
            for issue in self.issues:
                print(f"::error file={issue.path},title={issue.code}::{issue.message}")
        else:
            for issue in sorted(self.issues, key=lambda item: (item.path, item.code)):
                print(f"ОШИБКА {issue.path} [{issue.code}] {issue.message}")
        print()
        print(f"Контрактных ошибок: {len(self.issues)}")
        return 1 if self.issues else 0


def main() -> int:
    fmt = "github" if "--format=github" in sys.argv else "text"
    linter = ContractLinter()
    linter.run()
    return linter.report(fmt)


if __name__ == "__main__":
    raise SystemExit(main())
