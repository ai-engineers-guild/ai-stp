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

# Отсутствие bun обязано валить рецепт, а не пропускать шаг.
bunreq := "bun --version"

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
setup-docs: setup-python
    {{py}} {{scripts}}/npm_ci.py

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

# Собирает, но не публикует, пять публичных Python-пакетов. Рабочее дерево
# обязано быть чистым; локальная характеризация dirty tree запускается напрямую
# с явным `--allow-dirty` и никогда не является release evidence.
release-candidate:
    uv run --locked python release_scripts/build_candidate.py --replace

# Устанавливает именно пять wheel текущего candidate, запускает CLI вне checkout
# и удаляет tool. Public index используется только для внешних зависимостей.
release-candidate-install:
    uv run --locked python -m release_scripts.verify_candidate_install \
        dist/release-candidate \
        --expected-sha "$(git rev-parse HEAD)"

# Read-only audit of the live GitHub release controls. It is expected to fail
# closed until the repository is public and every control in #188 is active.
release-protections:
    uv run --locked python release_scripts/verify_protections.py

# Ничего не меняет и ничем не аутентифицируется: анонимный срез обязан
# доказываться без учётных данных, а скрипт, который не может их держать, не
# может их и раскрыть. Не входит в `just check` — гейт репозитория не вправе
# зависеть от внешней среды, иначе её недоступность читается как красный код.
#
# Доказывает анонимный срез `#85` против развёрнутой среды.
evidence-live origin="https://nddev.asia" commit="":
    uv run --locked python -m release_scripts.verify_live_slice \
        --origin "{{origin}}" \
        {{ if commit == "" { "" } else { "--expected-commit " + commit } }}

# Доказывает срез синхронизации двух устройств против развёрнутой среды (#180).
# Оба home должны быть уже авторизованы: device-code flow требует человека, и
# скрипт, умеющий выпустить сессию, доказывал бы не тот путь.
#
# Разный `HOME` НЕ делает два устройства. Хранилище учётных данных операционной
# системы принадлежит пользователю ОС, а не домашнему каталогу: `HOME=… ai-stp
# auth status` отвечает `authenticated` из общего keyring, и оба «устройства»
# оказываются одним. Каждый вход должен выполняться с
# `AI_STP_FORCE_FILE_CREDENTIAL_STORE=1`, иначе срез доказывает не то.
evidence-sync home_a home_b origin="https://nddev.asia":
    uv run --locked python -m release_scripts.verify_sync_slice \
        --origin "{{origin}}" \
        --home-a "{{home_a}}" \
        --home-b "{{home_b}}"

# Доказывает публикацию, гранты, отчёты и чтения владельца против развёрнутой
# среды (#182). По умолчанию только читающая половина: публикация неизменяемой
# версии и изменение чужого доступа требуют явного решения оператора.
evidence-publication home origin="https://nddev.asia" writes="":
    uv run --locked python -m release_scripts.verify_publication_slice \
        --origin "{{origin}}" \
        --home "{{home}}" \
        {{ if writes == "" { "" } else { "--allow-writes" } }}

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

# Реальный render диаграмм в движке Mermaid, а не разбор их текста.
docs-regress:
    {{py}} {{scripts}}/mermaid_check.py

docs-serve:
    {{py}} -m mkdocs serve -f {{scripts}}/mkdocs.yml

user-docs-build:
    {{py}} -m mkdocs build --strict -f {{scripts}}/user-mkdocs.yml

user-docs-serve:
    {{py}} -m mkdocs serve -f {{scripts}}/user-mkdocs.yml

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
    {{run}} pyright
    {{run}} python -m release_scripts.public_export --report
    {{run}} python -m ai_stp_contracts.schemas --check schemas/v1
    {{run}} python -m ai_stp_contracts.web_projections --check
    {{run}} python release_scripts/provider_kit.py --check provider-kit/v3
    {{py}} {{scripts}}/skill_projections.py --check

# Порог покрытия задан в pyproject и является частью этого рецепта.
back-test:
    {{run}} pytest {{ if test_workers == "0" { "" } else { "-n " + test_workers } }}
    # Порог проверяется второй раз, по записанным данным покрытия. Причина не
    # теоретическая: прогон CI на letya999@6a41c28 напечатал ровно строку
    # `FAIL Required test coverage of 95% not reached. Total coverage: 94.55%`,
    # продолжил следующим рецептом и завершился успехом на уровне step, job и
    # run. Локально та же цепочка на тех же закреплённых версиях (pytest 9.1.1,
    # pytest-cov 7.1.0, coverage 7.15.3) корректно возвращает 1, поэтому
    # механизм расхождения не воспроизведён. Пока он неизвестен, гейт не должен
    # зависеть только от кода возврата pytest: этот вызов перечитывает данные и
    # отказывает сам.
    {{run}} coverage report --precision=2 --fail-under=90

# SQLite emits its direct ResourceWarning only on Python 3.13+ finalization.
# Run the focused long-lived CLI lifecycle with both warning forms as errors;
# the broad suite also owns platform logging handlers, whose lifecycle belongs
# to the platform track and must not weaken this CLI-specific acceptance gate.
back-resource:
    {{run}} pytest --no-cov -q \
        -W error::ResourceWarning \
        -W error::pytest.PytestUnraisableExceptionWarning \
        tests/contract/test_cli_resource_lifecycle.py

# Каталог очищается перед сборкой: колесо снятой версии, оставшееся от прошлого
# прогона, иначе доступно установщику через --find-links и подменит собой новое.

# Колёса всех пакетов workspace в dist/ (каталог git-ignored).
back-build:
    {{run}} python -c "import shutil; shutil.rmtree('dist', ignore_errors=True)"
    uv build --all-packages --out-dir dist -q

# Рабочее окружение содержит зависимости групп docs и dev, поэтому необъявленная
# зависимость пакета в нём не видна и проявляется только у того, кто поставил
# колесо: так уже прошёл незамеченным импорт yaml в apps/cli. Второй способ —
# ровно та команда, которую обещает лендинг: он проверяет точку входа на PATH,
# работу вне исходного дерева и границу удаления.

# Ставит собранные колёса и запускает CLI двумя способами.
back-regress:
    {{ if os() == "windows" { "Write-Error 'back-regress requires bash; run this gate on Linux or macOS'; exit 1" } else { "just _back-regress-posix" } }}

_back-regress-posix: back-build
    #!/usr/bin/env bash
    set -euo pipefail
    dist="$PWD/dist"
    work="$(mktemp -d)"
    tool="$(mktemp -d)"
    trap 'rm -rf "$work" "$tool"' EXIT

    # XDG не изолирует системное хранилище учётных данных: оно принадлежит
    # пользователю, а не домашнему каталогу. Без этой строки полоса писала ключ
    # в реальный keyring разработчика и однажды заменила там рабочую запись.
    # Адрес шины уводится в никуда, поэтому Secret Service не отвечает и CLI
    # уходит на файловый ярус. Явный продуктовый переключатель ниже нужен и на
    # macOS, где DBus не управляет Keychain, и не даёт release regression
    # открыть настоящий locker пользователя ни на одной поддерживаемой ОС.
    export DBUS_SESSION_BUS_ADDRESS="unix:path=$work/no-such-bus"
    # Windows Credential Manager is available even when DBus is absent. Keep
    # this disposable regression environment on the explicit file tier there.
    export AI_STP_FORCE_FILE_CREDENTIAL_STORE="1"

    uv venv "$work/venv" -q
    # `UV_PYTHON` belongs to the outer CI matrix and intentionally points at
    # that job's interpreter.  It must not redirect this clean-install probe
    # back into the job environment.  `--python` owns the destination
    # explicitly and is portable because uv accepts a venv directory.
    # Every workspace package currently shares the development version 0.1.0.
    # A name-only install may therefore resolve an older public 0.1.0 wheel
    # instead of the wheel built from this checkout. Pass every internal wheel
    # as a direct requirement so this probe verifies one coherent candidate.
    uv pip install --python "$work/venv" -q \
        "$dist"/ai_stp_foundation-*.whl \
        "$dist"/ai_stp_passports-*.whl \
        "$dist"/ai_stp_assurance-*.whl \
        "$dist"/ai_stp_contracts-*.whl \
        "$dist"/ai_stp_cli-*.whl

    # venv раскладывается по-разному: bin/ на POSIX, Scripts/ и .exe на Windows.
    # Рецепт обязан выполняться на машине сопровождающего, а не только в CI,
    # иначе локальный и CI-путь расходятся вопреки AGENTS.md.
    if [ -d "$work/venv/Scripts" ]; then
        venv_bin="$work/venv/Scripts"; exe=".exe"
    else
        venv_bin="$work/venv/bin"; exe=""
    fi

    "$venv_bin/python$exe" -c 'import ai_stp_cli'
    # SPEC-011 REQ-1118 and the hard invariant in AGENTS.md: ai_stp calls no
    # model interface and needs no model key. Checked against the resolved
    # closure a user actually installs, not against the declared list — a model
    # client arriving transitively would be just as much of a violation.
    if uv pip list --python "$work/venv" 2>/dev/null \
        | grep -iE '^(anthropic|openai|cohere|mistralai|litellm|ollama|google-generativeai|google-genai|langchain|llama-index|transformers|tiktoken)\b'; then
        echo "back-regress: a model client is in the dependency closure (SPEC-011 REQ-1118)" >&2
        exit 1
    fi
    # Ровно те вызовы, которые критерии приёмки #72 требуют от установленного
    # колеса. Каждый обязан завершиться нулём, поэтому set -e здесь и работает.
    for argv in "--help" "version" "doctor" "help --agent --json"; do
        XDG_CONFIG_HOME="$work/config" XDG_DATA_HOME="$work/data" \
            "$venv_bin/ai-stp$exe" $argv > /dev/null
    done
    echo "back-regress: колесо устанавливается и запускается в чистом окружении"

    export UV_TOOL_DIR="$tool/tools" UV_TOOL_BIN_DIR="$tool/bin"
    export XDG_CONFIG_HOME="$tool/home/config" XDG_DATA_HOME="$tool/home/data" HOME="$tool/home"
    # platformdirs uses these native locations on Windows instead of XDG_*.
    export APPDATA="$tool/home/AppData/Roaming" LOCALAPPDATA="$tool/home/AppData/Local"
    export USERPROFILE="$tool/home"
    uv tool install -q "$dist"/ai_stp_cli-*.whl \
        --with "$dist"/ai_stp_foundation-*.whl \
        --with "$dist"/ai_stp_passports-*.whl \
        --with "$dist"/ai_stp_assurance-*.whl \
        --with "$dist"/ai_stp_contracts-*.whl
    cd "$tool"
    "$tool/bin/ai-stp$exe" doctor --json > /dev/null
    "$tool/bin/ai-stp$exe" help --agent --json > /dev/null
    "$tool/bin/ai-stp$exe" passport developer init --json > /dev/null
    # Изоляция проверяется, а не предполагается: если ярус вдруг окажется
    # системным, полоса упадёт здесь, вместо того чтобы молча загрязнить
    # хранилище разработчика.
    tier="$(AI_STP_FORCE_FILE_CREDENTIAL_STORE=1 "$tool/bin/ai-stp$exe" device show --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["credential_store"])')"
    if [ "$tier" != "file" ]; then
        echo "back-regress: ожидался файловый ярус, получен $tier — изоляция не работает" >&2
        exit 1
    fi
    test -f "$tool/home/data/ai-stp/registry.sqlite"
    # Находка ревью: колесо не несло канонический Agent Skill вовсе, поэтому
    # установленный продукт отдавал агенту двоичный файл и никакой процедуры.
    # Проверяется на установке вне дерева исходников — там, где репозиторную
    # копию взять неоткуда.
    mkdir -p "$tool/harness"
    "$tool/bin/ai-stp$exe" skill install --target "$tool/harness" --harness claude-code --json > /dev/null
    test -f "$tool/harness/SKILL.md"
    grep -q "ai-stp doctor --json" "$tool/harness/SKILL.md"
    owned="$("$tool/bin/ai-stp$exe" skill status --target "$tool/harness" --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["state"])')"
    if [ "$owned" != "owned" ]; then
        echo "back-regress: установленный Skill не признан своим ($owned)" >&2
        exit 1
    fi
    "$tool/bin/ai-stp$exe" skill remove --target "$tool/harness" --json > /dev/null
    test ! -e "$tool/harness/SKILL.md"
    uv tool uninstall -q ai-stp-cli
    test ! -e "$tool/bin/ai-stp$exe"
    # Удаление снимает только принадлежащие CLI файлы. Локальные данные — это
    # отдельное явное действие пользователя.
    test -f "$tool/home/data/ai-stp/registry.sqlite"
    echo "back-regress: uv tool install и uninstall работают, данные пользователя сохраняются"

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
    cd apps/web && bunx playwright install chromium
    cd apps/web && bun run test:e2e

# Две независимые production-сборки доказывают build-time исключение feature.
web-feature-profiles:
    {{bunreq}}
    cd apps/web && bunx playwright install chromium
    cd apps/web && bun run test:feature-profiles

# Сборка идёт первой намеренно. `tsconfig` включает `.next/types/**/*.ts` —
# валидатор маршрутов, который порождает `next build`. Пока сборка шла после
# статики, этот include не значил ничего в чистом checkout (каталога нет, шаблон
# не совпадает ни с чем) и давал ложный отказ локально, где каталог остался от
# другой ветки. `just` выполняет каждый рецепт один раз, поэтому порядок ничего
# не удорожает: сборка всё равно в этом же агрегате.
web-check: web-build web-storybook web-static web-test web-regress web-feature-profiles
