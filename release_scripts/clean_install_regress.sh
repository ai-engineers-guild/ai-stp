#!/usr/bin/env bash
# Install the built wheels and run the CLI two ways, outside the checkout.
#
# The single owner of the clean-install regression. `just back-regress` calls
# it locally and the CI gate calls it directly, so the probe cannot drift
# between the two paths the way a recipe body copied into workflow YAML would.
#
# Requires bash. Locally `just back-regress` finds it through
# `release_scripts/run_bash.py` (Git for Windows, not WSL). CI calls this
# file directly on a POSIX runner. Needs a populated dist/ from
# `uv build --all-packages --out-dir dist`.
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
    echo "clean_install_regress: a model client is in the dependency closure (SPEC-011 REQ-1118)" >&2
    exit 1
fi
# Ровно те вызовы, которые критерии приёмки #72 требуют от установленного
# колеса. Каждый обязан завершиться нулём, поэтому set -e здесь и работает.
for argv in "--help" "version" "doctor" "help --agent --json"; do
    XDG_CONFIG_HOME="$work/config" XDG_DATA_HOME="$work/data" \
        "$venv_bin/ai-stp$exe" $argv > /dev/null
done
echo "clean_install_regress: колесо устанавливается и запускается в чистом окружении"

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
    echo "clean_install_regress: ожидался файловый ярус, получен $tier — изоляция не работает" >&2
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
    echo "clean_install_regress: установленный Skill не признан своим ($owned)" >&2
    exit 1
fi
"$tool/bin/ai-stp$exe" skill remove --target "$tool/harness" --json > /dev/null
test ! -e "$tool/harness/SKILL.md"
uv tool uninstall -q ai-stp-cli
test ! -e "$tool/bin/ai-stp$exe"
# Удаление снимает только принадлежащие CLI файлы. Локальные данные — это
# отдельное явное действие пользователя.
test -f "$tool/home/data/ai-stp/registry.sqlite"
echo "clean_install_regress: uv tool install и uninstall работают, данные пользователя сохраняются"
