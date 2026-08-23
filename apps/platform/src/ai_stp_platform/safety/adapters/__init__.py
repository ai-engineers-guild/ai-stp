"""Engine adapters: one module per check_id primary."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome

AdapterFn = Callable[[Path, ArtifactManifest, CheckSpec], CheckOutcome]


def get_adapter(check_id: str) -> AdapterFn | None:
    from ai_stp_platform.safety.adapters import (
        agentic_behavior,
        bandit,
        cargo_audit,
        cargo_deny,
        clamav,
        content_hidden,
        eslint_security,
        gitleaks,
        gosec,
        govulncheck,
        hook_static,
        mcp_config,
        network_intent,
        npm_audit,
        opengrep,
        osv,
        path_denylist,
        pdf_document,
        pi_content,
        pip_audit,
        secrets_heuristic,
        setup_aggregate,
        shell_obfuscation,
        shellcheck,
        skill_gate,
        unpack,
        yara_scan,
    )

    table: dict[str, AdapterFn] = {
        "agentic_behavior": agentic_behavior.run,
        "artifact_unpack": unpack.run,
        "path_denylist": path_denylist.run,
        "secrets_heuristic": secrets_heuristic.run,
        "secrets_gitleaks": gitleaks.run,
        "pi_content_pack": pi_content.run,
        "content_hidden": content_hidden.run,
        "sast_opengrep": opengrep.run,
        "mcp_config_static": mcp_config.run,
        "network_intent": network_intent.run,
        "hook_schema_static": hook_static.run_schema,
        "hook_command_argv": hook_static.run_command,
        "skill_static_gate": skill_gate.run,
        "shell_obfuscation": shell_obfuscation.run,
        "sast_shellcheck": shellcheck.run,
        "sast_bandit": bandit.run,
        "sca_pip_audit": pip_audit.run,
        "sast_gosec": gosec.run,
        "sca_govulncheck": govulncheck.run,
        "sca_cargo_audit": cargo_audit.run,
        "sca_cargo_deny": cargo_deny.run,
        "sast_eslint_security": eslint_security.run,
        "sca_npm_audit": npm_audit.run,
        "document_pdf": pdf_document.run,
        "sca_osv": osv.run,
        "malware_clamav": clamav.run,
        "malware_yara": yara_scan.run,
        "setup_pin_aggregate": setup_aggregate.run,
    }
    return table.get(check_id)
