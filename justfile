# Единая точка входа для локальных и CI-проверок.
#
# Файл держится на дуальности: `gen` пишет, `check` читает. Всё остальное —
# те же операции, суженные до одной группы.
#
# Группа — это владелец проверки, и префикс обязателен:
#   docs-*  — документационное основание (specs, ADR, docs/, MkDocs);
#   back-*  — Python: packages/, apps/api, apps/platform, apps/cli, tests/;
#   web-*   — apps/web.
#
# У каждой группы один и тот же набор глаголов, поэтому команду можно вывести,
# а не помнить:
#   <группа>-gen      переписать машинный текст (формат и порождённые артефакты);
#   <группа>-static   прочитать исходник, не запуская его;
#   <группа>-test     прогнать тесты;
#   <группа>-build    собрать артефакт;
#   <группа>-regress  прогнать собранный артефакт в реальном движке;
#   <группа>-check    агрегат группы.
#
# Никакой `-check` ничего не пишет: расхождение порождённого с источником
# ловится в `-static` и чинится явным вызовом `-gen`.

scripts := "docs_scripts"
py := "uv run --locked --group docs python"
run := "uv run --locked"
# Test processes. The fleet class that runs the gate is a 4-vCPU machine, so 4
# is the shape CI actually has; a laptop with more cores can raise it and a
# constrained one can set 0 to go back to a single process. `auto` is
# deliberately not the default: it reads the host's core count, and on a
# 12-core machine that starts twelve workers against 8 GiB of memory.
test_workers := env_var_or_default("AI_STP_TEST_WORKERS", "4")

# xdist scheduling granularity. `load` (the plugin default) sends individual
# tests to whichever worker is free; that is the right shape here because the
# suite has no cross-test coupling — every PostgreSQL test owns its database
# and the root conftest isolates everything else per test. Coarser modes
# (`loadfile`, `loadgroup`) exist for local diagnosis of a skewed tail and are
# selected explicitly, not by default.
test_dist := env_var_or_default("AI_STP_TEST_DIST", "load")

# Coverage tracing backend. `ctrace` is the historical default; `sysmon`
# (Python 3.12+ sys.monitoring) traces with far less interpreter overhead.
# Exported so a focused run sees the same backend as the gate. pyproject pins
# `core = "sysmon"` and must not list greenlet under concurrency — that pair
# made coverage fall back to ctrace with a warning per worker (ADR-0117).
export COVERAGE_CORE := env_var_or_default("AI_STP_TEST_COVERAGE_CORE", "sysmon")

# Отсутствие bun обязано валить рецепт, а не пропускать шаг. Версия проверяется
# точно: bun пишет lockfile в формате своей линии, и `bun install` из другой
# версии молча переписывает `bun.lock` в то, что гейт прочитать не может.
# Ошибка тогда всплывает в CI, а не здесь.
bunreq := 'test "$(bun --version)" = "$(cat .bun-version)" || { echo "bun $(cat .bun-version) required, found $(bun --version 2>/dev/null || echo none)" >&2; exit 1; }'

# То же для uv, но по другой причине и только на сборщике. uv штампует свою
# версию в `dist-info/WHEEL`, поэтому кандидат, собранный другой версией,
# отличается от выпускаемого — при полностью совпадающих модулях. Один раз это
# уже стоило разбирательства: десять несовпавших digest'ов оказались одной
# строкой `Generator:`, и версия читалась как подмена байтов.
uvreq := 'have=$(uv --version 2>/dev/null | cut -d" " -f2); want=$(cat .uv-version); test "$have" = "$want" || { echo "uv $want required, found ${have:-none}; get it with: bash .github/scripts/install-uv.sh $want <dir> && export PATH=<dir>:\$PATH" >&2; exit 1; }'

export PYTHONUTF8 := "1"

default:
    @just --list --unsorted

# Здесь же ловится рассинхрон lock-файлов: все три ставятся строго по ним.

# Готовит окружение целиком: Python, Node-инструменты документации и веб.
# Готовит окружение целиком. Осталась агрегатом, потому что локально нужен
# именно он: один вызов перед `just check`, который готовит всё.
#
# Разделён на три части не ради вкуса. В CI гейт исполняется несколькими job, и
# job, которому нужен только Python, ставил Node, bun и зависимости веба —
# измеренно 1 м 35 с на `setup-node` и 1 м 55 с на кэш bun, каждый раз впустую
# (`ADR-0105`).
setup: setup-python setup-docs setup-web

# Python-окружение: всё, что исполняет `uv run`.
setup-python:
    uv sync --locked --group docs --group dev

# Node-инструменты документации: markdownlint и движок Mermaid.
setup-docs:
    {{bunreq}}
    cd docs_scripts && bun install --frozen-lockfile

# Зависимости веба.
setup-web:
    {{bunreq}}
    cd apps/web && bun install --frozen-lockfile

hooks:
    python {{scripts}}/install_hooks.py

# Всё, что пишет. Итоговый diff смотрится руками.
gen: docs-gen back-gen web-gen

# Всё, что читает.
check: docs-check back-check web-check security

# Быстрый гейт для git-хука коммита: документация и статический Python-анализ.
# Тысячи backend-тестов, сборка wheels и install-regression остаются в полном
# `back-check`, который запускается на push и в CI.
pre-commit: docs-check back-static

# Общий для репозитория, а не групповой: сканер пока один. Python-сканер
# добавляется сюда же, когда будет выбран, а не пустым рецептом заранее.

# Условия редистрибуции, записанные внутри каждого отслеживаемого шрифта.
# Намеренно вне `just check`: остаётся ли restricted-шрифт в репозитории — это
# лицензионное решение владельца со своей ценой, и падающий сегодня гейт принял
# бы его за него. `--strict` возвращает ненулевой код и предназначен release-гейту
# после того, как решение принято. fonttools подаётся через `--with` и в lockfile
# проекта не попадает: разовый аудит не должен весить на каждой установке.
fonts-licence *args:
    uv run --no-project --with fonttools --with brotli \
        python {{scripts}}/font_licence_audit.py {{args}}

# Скан зависимостей на известные уязвимости.
security:
    {{bunreq}}
    cd apps/web && bun run audit

# Offline check of one `ai-stp-estate-release/1` record (`docs/contracts/estate-release.md`).
estate-validate path:
    {{run}} python -m release_scripts.validate_estate_record "{{path}}"

# Deterministic safety evidence; the script disables external CLI and network.
safety-benchmark *args:
    {{run}} python scripts/safety/benchmark_offline.py {{args}}

# 108 real filesystem fixtures, sequential platform backend scan, JSON evidence.
safety-corpus *args:
    {{run}} python scripts/safety/run_adversarial_corpus.py {{args}}

# Собирает, но не публикует, пять публичных Python-пакетов. Рабочее дерево
# обязано быть чистым; локальная характеризация dirty tree запускается напрямую
# с явным `--allow-dirty` и никогда не является release evidence.
release-candidate:
    {{uvreq}}
    uv run --locked python release_scripts/build_candidate.py --replace

# Устанавливает именно пять wheel текущего candidate, запускает CLI вне checkout
# и удаляет tool. Public index используется только для внешних зависимостей.
release-candidate-install:
    uv run --locked python -m release_scripts.verify_candidate_install \
        dist/release-candidate \
        --expected-sha "$(git rev-parse HEAD)"

# Verifies the anonymous slice (`#85`) against the deployed environment.
#
# Changes nothing and authenticates with nothing: an anonymous slice has to prove
# itself without credentials, and a script that cannot hold one cannot leak one.
# Not part of `just check` — the repository gate may not depend on an external
# environment, or that environment being unreachable reads as a red build here.
evidence-live origin="https://ai-stp.aiguild.space" commit="":
    uv run --locked python -m release_scripts.verify_live_slice \
        --origin "{{origin}}" \
        {{ if commit == "" { "" } else { "--expected-commit " + commit } }}

# Verifies the two-device synchronisation slice (#180) against the deployed
# environment. Both homes must already be signed in: the device-code flow needs a
# person, and a script able to mint a session would be proving the wrong path.
#
# Different `HOME` values do NOT create two devices. The OS credential store
# belongs to the OS user, not the home directory, so `HOME=… ai-stp auth status`
# answers `authenticated` from the shared keyring and both "devices" turn out to
# be one. Each login must use `AI_STP_FORCE_FILE_CREDENTIAL_STORE=1`, or the
# slice proves something other than what it claims.
#
# `skip` is a space-separated list of exact event ids that no client can apply to
# this account's history. The operator names them: a slice that guessed what to
# skip would go green on the strength of what it never read.
evidence-sync home_a home_b origin="https://ai-stp.aiguild.space" skip="":
    uv run --locked python -m release_scripts.verify_sync_slice \
        --origin "{{origin}}" \
        --home-a "{{home_a}}" \
        --home-b "{{home_b}}" \
        {{ if skip == "" { "" } else { prepend("--skip-event ", skip) } }}

# Доказывает, что таблица проекций этого репозитория всё ещё согласна с семью
# провайдерами **как выпущенными** — на байтах, которые отдаёт `provider fetch`.
#
# Не входит в `just check` по той же причине, что и остальные срезы: гейт не
# вправе зависеть от чужих тегов, иначе недоступность релиза читается как
# красный код здесь.
#
# Существует потому, что 2026-08-27 обе наши таблицы назвали поверхность cursor,
# которую продукт не читает, а сравнивающая их проверка прошла — они были
# неверны одинаково. Решила только декларация провайдера, и ни одна проверка не
# сверялась с **релизом**: аналог в наборе тестов читает локальное дерево
# сборки, то есть то, что человек последним скомпилировал.
#
# Требует `GH_CONFIG_DIR`: срез изолирует `HOME`, а `provider fetch` вызывает
# `gh`, который в изоляции не находит конфигурацию и сообщает об отсутствии
# метаданных релиза — не о причине.
evidence-providers tag harness="":
    GH_CONFIG_DIR="${GH_CONFIG_DIR:-${APPDATA:+$APPDATA/GitHub CLI}}"; \
    GH_CONFIG_DIR="${GH_CONFIG_DIR:-$HOME/.config/gh}" \
    uv run --locked python -m release_scripts.verify_provider_slice \
        --tag "{{tag}}" \
        {{ if harness == "" { "" } else { prepend("--harness ", harness) } }}

# Drives every non-global provider profile through a mutating disposable-target
# lifecycle with a consumer-produced adaptation-bound bundle v2. This is local
# source evidence before release; `evidence-providers` remains the released-byte
# proof after attestation and publication.
evidence-provider-scopes setup_systems_root:
    uv run --locked python -m release_scripts.verify_scoped_provider_slice \
        --setup-systems-root "{{setup_systems_root}}"

# Вторая половина того же вопроса: `evidence-providers` доказывает контракт и
# байты, а этот срез ведёт каждый выпущенный провайдер через **потребительский**
# путь — `harness install/status/update/remove` вызовами самого `ai-stp`.
#
# Это разные вопросы, и они падают по разным причинам. Все дефекты интеграции
# этого хозяйства жили ровно между потребителем и провайдером: argv, которого
# провайдер не ждал; статус, прочитанный иначе; запись, не пережившая песочницу;
# постусловие, снятое не с того субъекта. Ни один из них не виден срезу,
# который спрашивает провайдера напрямую.
#
# Строка на харнесс, исход из пяти, и отсутствующая строка — ошибка, а не ноль
# отказов. `GH_CONFIG_DIR` нужен по той же причине, что и соседу.
evidence-software tag harness="" acquire="":
    GH_CONFIG_DIR="${GH_CONFIG_DIR:-${APPDATA:+$APPDATA/GitHub CLI}}"; \
    GH_CONFIG_DIR="${GH_CONFIG_DIR:-$HOME/.config/gh}" \
    uv run --locked python -m release_scripts.verify_software_slice \
        --tag "{{tag}}" \
        {{ if harness == "" { "" } else { prepend("--harness ", harness) } }} \
        {{ if acquire == "" { "" } else { "--acquire" } }}

# Третий вопрос той же пары, и единственный про **конфигурацию**.
# `evidence-providers` спрашивает контракт, `evidence-software` — программу,
# а этот ведёт нативную поверхность каждого харнесса через полную дугу:
# посев → adopt → release → propose → confirm → plan → approve → apply →
# наблюдение цели → план удаления → apply → цель снова чиста.
#
# Существует потому, что до него сквозное свойство вижена — «захватить
# конфигурацию машины и поставить её на следующей» — измерялось руками и
# только на linux/x86_64. Вердикт снимается с цели, а не с ответа провайдера.
#
# В `just check` не входит по той же причине, что и соседи: гейт не вправе
# зависеть от чужого релиза. `GH_CONFIG_DIR` нужен `provider fetch`.
evidence-config tag harness="" from_import="" scope="":
    GH_CONFIG_DIR="${GH_CONFIG_DIR:-${APPDATA:+$APPDATA/GitHub CLI}}"; \
    GH_CONFIG_DIR="${GH_CONFIG_DIR:-$HOME/.config/gh}" \
    uv run --locked python -m release_scripts.verify_config_slice \
        --tag "{{tag}}" \
        {{ if harness == "" { "" } else { prepend("--harness ", harness) } }} \
        {{ if from_import == "" { "" } else { "--from-import" } }} \
        {{ if scope == "" { "" } else { "--scope " + scope } }}

# Приёмка `#54`: один MCP-компонент в трёх нативных формах — ключ в чужом
# файле настроек, собственный файл, и продукт, у которого такого вида нет.
#
# Скрипт существовал с 2026-08-31 и не вызывался ниоткуда: ни рецепта, ни шага
# workflow, ни строки в документе. Первый настоящий запуск нашёл в нём три
# дефекта — усыновление из произвольного каталога, версия, которой adopt не
# возвращает, и контроль claude-code, зеленевший на чужом отказе.
evidence-contribution tag:
    GH_CONFIG_DIR="${GH_CONFIG_DIR:-${APPDATA:+$APPDATA/GitHub CLI}}"; \
    GH_CONFIG_DIR="${GH_CONFIG_DIR:-$HOME/.config/gh}" \
    uv run --locked python -m release_scripts.verify_contribution_slice \
        --tag "{{tag}}"

# Спрашивает у источника, разошёлся ли корпус первого лица с тем, что
# опубликовано. Сорок объектов корпуса привязаны к `passport_digest` и
# неизменяемы по `REQ-2606` — то есть защищены от того, чтобы их **изменили**,
# и ничем от того, чтобы они были **неверны**. Локально их не перевывести:
# содержимое живёт в семи чужих репозиториях.
#
# Разница между двумя защитами не теоретическая: 2026-08-29 корпус нёс семь
# сетапов из двадцати восьми опубликованных, под именем роли, которого нет ни в
# одном источнике, — и все digest'ы сходились всё это время (`#461`).
#
# Рецепт заведён потому, что до него это умел только тот, кто наберёт путь к
# скрипту. Он сообщает и никогда не отказывает, и в `just check` не входит:
# гейт репозитория не вправе зависеть от чужой сети.
corpus-drift *args:
    uv run --locked python release_scripts/build_first_party_corpus.py --drift \
        --out packages/contracts/src/ai_stp_contracts/first_party/v1 {{args}}

# Фетчит каждую ссылку, на которой стоит строка каталога харнессов, и называет
# мёртвые. Ничто в репозитории ссылку не открывает, поэтому протухшую находит
# человек и больше никто: 2026-08-28 таких оказалось четыре, две из них
# написаны в тот же день по образцу соседей, а не с открытой страницы.
#
# Не в гейте по той же причине, что и остальные срезы: `just check` не вправе
# зависеть от того, что сайт вендора отвечает. 403, 405 и 429 считаются
# недоказанными, а не мёртвыми — часть хостов отказывает скрипту на HEAD.
evidence-citations:
    uv run --locked python -m release_scripts.verify_citation_slice

# Verifies publication, grants, reports and owner reads against the deployed
# environment (#182). Read-only by default: publishing an immutable version and
# changing somebody else's access both need an explicit decision by the operator.
evidence-publication home origin="https://ai-stp.aiguild.space" writes="" invite="":
    uv run --locked python -m release_scripts.verify_publication_slice \
        --origin "{{origin}}" \
        --home "{{home}}" \
        {{ if writes == "" { "" } else { "--allow-writes" } }} \
        {{ if invite == "" { "" } else { prepend("--invite-email ", invite) } }}

# --- docs ---------------------------------------------------------------

# Перегенерирует оглавления и таблицы документации.
docs-gen:
    {{py}} {{scripts}}/docs_lint.py --fix

# Frontmatter, ссылки, anchors, placeholders, паритет index.md, структура и
# трассируемость active specs, семантические регрессии, Markdown и YAML.

# Статические проверки документации одним прогоном.
docs-static:
    {{py}} {{scripts}}/docs_lint.py
    {{py}} {{scripts}}/spec_lint.py
    {{py}} {{scripts}}/contract_lint.py
    {{py}} {{scripts}}/run_markdownlint.py
    {{py}} -m yamllint -c {{scripts}}/.yamllint.yml .

# Unit-тесты самих документационных валидаторов.
docs-test:
    {{py}} -m unittest discover -s {{scripts}}/tests -v

docs-build:
    {{py}} -m mkdocs build --strict -f {{scripts}}/mkdocs.yml
    {{py}} -m mkdocs build --strict -f {{scripts}}/user-mkdocs.yml
    {{py}} -m mkdocs build --strict -f {{scripts}}/user-mkdocs.en.yml

# Реальный render диаграмм в движке Mermaid, а не разбор их текста.
docs-regress:
    {{py}} {{scripts}}/mermaid_check.py

docs-serve:
    {{py}} -m mkdocs serve -f {{scripts}}/mkdocs.yml

# Обе языковые линии. Английская собирается в `/en/` внутри того же site_dir,
# поэтому порядок важен: русская чистит каталог, английская кладётся внутрь.
user-docs-build:
    {{py}} -m mkdocs build --strict -f {{scripts}}/user-mkdocs.yml
    {{py}} -m mkdocs build --strict -f {{scripts}}/user-mkdocs.en.yml

user-docs-serve:
    {{py}} -m mkdocs serve -f {{scripts}}/user-mkdocs.yml

user-docs-serve-en:
    {{py}} -m mkdocs serve -f {{scripts}}/user-mkdocs.en.yml

docs-check: docs-static docs-test docs-build docs-regress

# --- back ---------------------------------------------------------------

# Формат исходников и оба порождаемых артефакта: schemas/v1 и проекции Skill.
back-gen:
    {{run}} ruff format .
    {{run}} python -m ai_stp_contracts.schemas schemas/v1
    {{run}} python -m ai_stp_contracts.web_projections
    {{run}} python release_scripts/provider_kit.py provider-kit/v3
    {{py}} {{scripts}}/skill_projections.py

# Формат, линт, типы и расхождение порождённого с источником одним прогоном.
# Что попадёт в публичный репозиторий `ai-stp`, и что попасть в него не может.
# Отчёт ничего не пишет и отказывает, если появился неназванный корень или
# приватная инфраструктура в публикуемом файле.
public-report:
    {{run}} python -m release_scripts.public_export --report

# Собирает публичное дерево в `public/build`: манифест, оверлей, свой git и
# пересобранные индексы.
public-build:
    {{run}} python -m release_scripts.public_export

# Публикует собранное дерево в `ai-stp` одним коммитом от identity из global
# git config. Дельта считается через API, поэтому скачивать ничего не нужно.
public-publish tree message:
    {{run}} python -m release_scripts.public_publish --tree "{{tree}}" --message-file "{{message}}"

# Забирает публичное дерево обратно сюда (`ADR-0110`). Аргумент — checkout
# `ai-stp`. Генераторы вызываются следом, потому что индексы публичного дерева
# перечисляют только его документы, а здесь их больше.
public-sync tree:
    {{run}} python -m release_scripts.public_import --tree "{{tree}}"
    just docs-gen
    just back-gen

# Показывает, что изменил бы синк, ничего не записывая.
public-sync-report tree:
    {{run}} python -m release_scripts.public_import --tree "{{tree}}" --report

# Проверяет, что опубликованная половина этого дерева совпадает с публичным
# репозиторием байт в байт. Это круговая проверка синка и экспорта сразу.
public-sync-verify tree:
    {{run}} python -m release_scripts.public_import --tree "{{tree}}" --verify

back-static:
    {{run}} ruff format --check .
    {{run}} ruff check .
    {{run}} python -m pyright
    {{run}} python -m release_scripts.public_export --report
    {{run}} python -m ai_stp_contracts.schemas --check schemas/v1
    {{run}} python -m ai_stp_contracts.web_projections --check
    {{run}} python release_scripts/provider_kit.py --check provider-kit/v3
    {{py}} {{scripts}}/skill_projections.py --check

# Coverage is printed, not a fail-under (ADR-0147). The second call reads
# the data pytest-cov wrote so the local log matches CI's combined report.
back-test:
    {{run}} python -m pytest {{ if test_workers == "0" { "" } else { "-n " + test_workers } }} --dist={{test_dist}}
    {{run}} python -m coverage report --precision=2

# Итерационный прогон без покрытия. Сбор покрытия стоит около трети времени
# гейта (ADR-0104: 325 с с ним против 252 с без), и в петле правка-запуск он не
# отвечает ни на один вопрос, который не ответил бы падающий тест. Гейтом не
# является: порог здесь не проверяется и проверяться не должен.
back-test-fast *args:
    {{run}} python -m pytest --no-cov {{ if test_workers == "0" { "" } else { "-n " + test_workers } }} --dist={{test_dist}} {{args}}

# Полный однопроцессный прогон с записью длительностей каждого теста в
# .test_durations. Файл питает duration-based шардирование, когда оно будет
# включено; без него шардирование падает на выравнивание по количеству тестов.
# Обновлять после крупных сдвигов состава набора, а не каждый прогон.
back-durations:
    {{run}} python -m pytest -n 0 --no-cov -q \
        --store-durations --durations-path .test_durations

# SQLite emits its direct ResourceWarning only on Python 3.13+ finalization.
# Run the focused long-lived CLI lifecycle with both warning forms as errors;
# the broad suite also owns platform logging handlers, whose lifecycle belongs
# to the platform track and must not weaken this CLI-specific acceptance gate.
back-resource:
    {{run}} python -m pytest --no-cov -q \
        -W error::ResourceWarning \
        -W error::pytest.PytestUnraisableExceptionWarning \
        tests/contract/test_cli_resource_lifecycle.py

# The cross-platform CLI surface, split the way the CI matrix consumes it.
# The flags are part of the contract and live here, not in the workflow YAML:
# `-vv` because addopts already carries `-q` and a single `-v` cancels out;
# `faulthandler_timeout` names the hanging test instead of ending mid-line,
# which is how three CI runs died on their own timeout without saying why.
# Local runs on one OS exercise the same invocation the three-OS matrix runs.
back-cli-suite suite:
    {{run}} python -m pytest "tests/{{suite}}" --no-cov -vv \
        -o faulthandler_timeout=300 {{ if test_workers == "0" { "" } else { "-n " + test_workers } }} --dist={{test_dist}} \
        {{ if suite == "unit" { "--ignore=tests/unit/platform --ignore=tests/unit/api" } else { "" } }}

# Каталог очищается перед сборкой: колесо снятой версии, оставшееся от прошлого
# прогона, иначе доступно установщику через --find-links и подменит собой новое.

# Колёса всех пакетов workspace в dist/ (каталог git-ignored).
back-build:
    {{run}} python -c "import shutil; shutil.rmtree('dist', ignore_errors=True)"
    uv build --all-packages --out-dir dist -q

# Ставит собранные колёса и запускает CLI двумя способами. Тело живёт в
# release_scripts/clean_install_regress.sh: его вызывает и этот рецепт, и CI
# гейт напрямую, поэтому чистая установка не может разойтись между локальным
# и CI-путём. Рабочее окружение содержит зависимости групп docs и dev,
# поэтому необъявленная зависимость пакета в нём не видна и проявляется
# только у того, кто поставил колесо: так уже прошёл незамеченным импорт yaml
# в apps/cli.
# Windows PATH `bash` is frequently WSL, which cannot run this checkout.
# `run_bash.py` locates Git-for-Windows bash (or PATH bash on POSIX) so the
# same recipe body is the local path; CI still calls the shell script itself.
back-regress:
    @just back-build
    {{run}} python release_scripts/run_bash.py release_scripts/clean_install_regress.sh

back-check: back-static back-test back-resource back-build back-regress

# --- web ----------------------------------------------------------------

# Формат исходников и типизированный клиент, порождённый из контракта.
web-gen:
    {{run}} python -m ai_stp_contracts.web_projections
    {{bunreq}}
    cd apps/web && bun run api:generate
    # The generator does not emit repository-Prettier form.  Formatting must
    # happen after generation so `just gen` is a deterministic clean producer
    # and `web-static` can validate its output without a repair step.
    cd apps/web && bun run format

# Запрет литерального пользовательского текста и паритет ru/en каталогов.
web-i18n:
    {{bunreq}}
    cd apps/web && bun run i18n:check

# ESLint, Prettier и TypeScript 7 одним прогоном.
web-static: web-i18n
    {{bunreq}}
    cd apps/web && bun run lint
    cd apps/web && bun run format:check
    cd apps/web && bun run type-check

# Покрытие меряется всегда: иначе его пороги были бы справочной цифрой, а не гейтом.

# Модульные и компонентные тесты.
web-test:
    {{bunreq}}
    cd apps/web && bun run test:coverage
    cd apps/web && bun run test:coverage:catalog

web-build:
    {{bunreq}}
    cd apps/web && AI_STP_WEB_PROFILE=public_saas bun run build

# Storybook собирается вместе с приложением, потому что у него другой сборочный
# граф: он свой Vite поднимает сам, через `viteFinal`. Пока его здесь не было,
# подъём `@vitejs/plugin-react` до 6 прошёл весь гейт зелёным и сломал только
# его — плагин требует Vite 8, приложение закреплено на 6, и увидеть это было
# негде. Одиннадцать секунд за то, чтобы такой разрыв назывался сразу.
web-storybook:
    {{bunreq}}
    cd apps/web && bun run build-storybook

# Сценарии в браузере поверх SaaS production-сборки, desktop и мобильный viewport.
#
# Сборка объявлена зависимостью, а не повторена телом. Раньше рецепт вызывал
# `bun run build` сам, поэтому внутри `web-check` production-сборка одного и
# того же профиля выполнялась дважды подряд: `just` выполняет один раз рецепт,
# а не одинаковую команду в двух телах. Разница измерена — 45 с локально и
# около полутора минут на четырёхъядерной машине флота, каждый прогон.
#
# Самостоятельный `just web-regress` при этом не изменился: зависимость даёт
# ту же сборку, которую рецепт делал сам.
web-regress: web-build
    {{bunreq}}
    # Browser bytes belong to the user's Playwright cache. OS packages belong
    # to the runner image and are provisioned out of band: a repository check
    # may not invoke sudo or block waiting for an administrator password.
    bash .github/scripts/ensure-chrome.sh
    cd apps/web && bun run test:e2e

# Две независимые production-сборки доказывают build-time исключение feature.
web-feature-profiles:
    {{bunreq}}
    bash .github/scripts/ensure-chrome.sh
    cd apps/web && bun run test:feature-profiles

# Сборка идёт первой намеренно. `tsconfig` включает `.next/types/**/*.ts` —
# валидатор маршрутов, который порождает `next build`. Пока сборка шла после
# статики, этот include не значил ничего в чистом checkout (каталога нет, шаблон
# не совпадает ни с чем) и давал ложный отказ локально, где каталог остался от
# другой ветки. `just` выполняет каждый рецепт один раз, поэтому порядок ничего
# не удорожает: сборка всё равно в этом же агрегате.
web-check: web-build web-storybook web-static web-test web-regress web-feature-profiles
