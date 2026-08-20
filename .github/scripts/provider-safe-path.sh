#!/usr/bin/env bash

# Deprioritize setup-python interpreters in the PATH inherited by provider fixtures.
# The toolcache interpreter needs its private library-path variable, while the
# provider boundary intentionally forwards only PATH and HOME. Leaving that
# interpreter first makes an otherwise self-contained `env python3` fixture
# fail before it can speak the provider protocol. The directories stay at the
# end because uv is installed beside that interpreter on a clean runner.
ai_stp_use_provider_safe_path() {
    local python_bin python_root entry safe_path="" deferred_path=""
    local -a path_entries
    python_bin="$(dirname "${UV_PYTHON:?UV_PYTHON must name the matrix interpreter}")"
    python_root="$(dirname "${python_bin}")"

    IFS=: read -r -a path_entries <<< "${PATH}"
    for entry in "${path_entries[@]}"; do
        case "${entry}" in
            "${UV_PROJECT_ENVIRONMENT:?UV_PROJECT_ENVIRONMENT must name the job environment}/bin"|"${python_bin}"|"${python_root}")
                deferred_path="${deferred_path:+${deferred_path}:}${entry}"
                ;;
            "")
                ;;
            *)
                safe_path="${safe_path:+${safe_path}:}${entry}"
                ;;
        esac
    done

    safe_path="${safe_path}${deferred_path:+:${deferred_path}}"

    test -n "${safe_path}" || {
        echo "provider-safe PATH would be empty" >&2
        return 1
    }
    export PATH="${safe_path}"
    command -v python3 >/dev/null || {
        echo "provider-safe PATH has no python3 fixture interpreter" >&2
        return 1
    }
    test "$(command -v python3)" != "${python_bin}/python3" || {
        echo "provider-safe PATH still selects the setup-python interpreter" >&2
        return 1
    }
    for entry in uv just; do
        command -v "${entry}" >/dev/null || {
            echo "provider-safe PATH has no ${entry}" >&2
            return 1
        }
    done
    # `uv run` prepends its project environment again. Pytest's repository-wide
    # isolation fixture restores this captured value before any provider spawn.
    export AI_STP_TEST_PROVIDER_PATH="${PATH}"
}
