use super::{Assessment, CAPABILITIES, Target};
use crate::{
    error::{Failure, Result},
    projection::Scope,
    provider::Info,
};
use serde_json::{Value, json};
use std::collections::BTreeSet;
use unicode_normalization::UnicodeNormalization;

fn strings(value: &Value) -> BTreeSet<&str> {
    value
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .collect()
}

fn limits(report: &mut Assessment, document: &Value, target: &Target) {
    for (field, code, value) in [
        ("supported_os", "os_unsupported", target.os.as_str()),
        ("supported_arch", "arch_unsupported", target.arch.as_str()),
    ] {
        let declared = strings(&document[field]);
        if !declared.is_empty() && !declared.contains(value) {
            report.refuse("compatibility",code,"the declared platforms do not cover this target",json!({"declared":declared.into_iter().collect::<Vec<_>>().join(", "),"target":value}));
        }
    }
    let versions = strings(&document["supported_harness_versions"]);
    if !versions.is_empty() && !versions.contains(target.harness_version.as_str()) {
        let unknown = target.harness_version.is_empty() || target.harness_version == "unknown";
        report.refuse("compatibility",if unknown {"harness_version_unknown"} else {"harness_version_unsupported"},
            "the observed version does not match an exact supported harness version",
            json!({"declared":versions.into_iter().collect::<Vec<_>>().join(", "),"target":if unknown {"none"} else {&target.harness_version}}));
    }
}

pub(super) fn compatibility<'a>(
    report: &mut Assessment,
    document: &'a Value,
    target: &Target,
) -> Result<Option<&'a Value>> {
    let mut scope = None;
    if document["kind"] == "setup" {
        if document["harness_id"] != target.harness_id {
            report.refuse(
                "compatibility",
                "harness_mismatch",
                "this setup belongs to another harness",
                json!({"declared":document["harness_id"],"target":target.harness_id}),
            );
        }
        limits(report, document, target);
    } else {
        let scope_name = match target.scope {
            Scope::Global => "global",
            Scope::Project => "project",
            Scope::UserRoot => "user_root",
        };
        let adaptations = document["adaptations"]
            .as_array()
            .ok_or_else(|| Failure::precondition("component adaptations missing"))?;
        scope = adaptations
            .iter()
            .find(|item| item["harness_id"] == target.harness_id)
            .and_then(|item| item["scope_adaptations"].as_array())
            .and_then(|items| items.iter().find(|item| item["scope"] == scope_name));
        match scope {
            Some(scope) => {
                if scope["technical_support"] == "unsupported" {
                    report.refuse(
                        "compatibility",
                        "adaptation_unavailable",
                        "the selected adaptation is unavailable",
                        json!({"harness_id":target.harness_id,"scope":scope_name}),
                    );
                }
                limits(report, scope, target);
            }
            None => report.refuse(
                "compatibility",
                "adaptation_unavailable",
                "this component has no explicit adaptation for the harness and scope",
                json!({"harness_id":target.harness_id,"scope":scope_name}),
            ),
        }
    }
    let capabilities: BTreeSet<_> = strings(&document["requires_capabilities"])
        .into_iter()
        .map(|s| {
            unicase::UniCase::new(s.nfc().collect::<String>().trim().to_owned()).to_folded_case()
        })
        .collect();
    for wanted in capabilities {
        let segments: Vec<_> = wanted.split('.').collect();
        let valid = wanted.chars().count() <= 64
            && (2..=4).contains(&segments.len())
            && segments.iter().all(|s| {
                !s.is_empty()
                    && !s.starts_with(['-', '_'])
                    && !s.ends_with(['-', '_'])
                    && s.chars()
                        .all(|c| c.is_alphanumeric() || matches!(c, '-' | '_'))
            });
        let (code, summary) = if !valid {
            (
                "capability_malformed",
                "a required capability identifier is malformed",
            )
        } else if !CAPABILITIES.contains(&wanted.as_str()) {
            (
                "capability_unknown",
                "a required capability is outside vocabulary 1.0",
            )
        } else if !target.capabilities.contains(&wanted) {
            (
                "capability_missing",
                "this target lacks a required capability",
            )
        } else {
            continue;
        };
        report.refuse("compatibility", code, summary, json!({"capability":wanted}));
    }
    Ok(scope)
}

pub(super) fn permissions(
    report: &mut Assessment,
    document: &Value,
    scope: Option<&Value>,
    target: &Target,
) {
    let mut required = BTreeSet::new();
    for source in std::iter::once(document).chain(scope) {
        for family in ["filesystem", "network", "process"] {
            for value in strings(&source["permissions"][family]) {
                required.insert(format!("{family}:{value}"));
            }
        }
    }
    for permission in required.difference(&target.permissions) {
        report.refuse(
            "entitlement",
            "entitlement_not_granted",
            "this target does not allow a required permission",
            json!({"permission":permission}),
        );
    }
    for entitlement in strings(&document["entitlements"]) {
        if !target.entitlements.contains(entitlement) {
            report.refuse(
                "entitlement",
                "entitlement_not_granted",
                "this target lacks a required entitlement",
                json!({"entitlement":entitlement}),
            );
        }
    }
}

pub(super) fn provider(
    report: &mut Assessment,
    document: &Value,
    scope: Option<&Value>,
    target: &Target,
    provider: Option<&Info>,
) {
    let provider = provider.filter(|info| info.document()["harness_id"] == target.harness_id);
    let Some(provider) = provider else {
        report.refuse(
            "provider",
            "provider_unavailable",
            "no validated provider declaration covers this harness",
            json!({"harness_id":target.harness_id}),
        );
        return;
    };
    if !provider.supports_platform(&target.os, &target.arch) {
        report.refuse(
            "provider",
            "provider_platform_unsupported",
            "the provider does not support this platform",
            json!({"platform":format!("{}/{}",target.os,target.arch)}),
        );
    }
    let missing = match scope {
        Some(scope) => !provider.supports_scope(target.scope, scope),
        None => document["kind"] == "setup" && !provider.supports_target(target.scope),
    };
    let known_unavailable = target.harness_id == "antigravity"
        && document["component_type"] == "command"
        && target.harness_version == "1.2.10";
    if missing || known_unavailable {
        report.refuse(
            "provider",
            "provider_surface_unavailable",
            "the provider cannot project this exact native surface",
            json!({"harness_id":target.harness_id}),
        );
    }
}

pub(super) fn notes(report: &mut Assessment, document: &Value, target: &Target) {
    let missing: BTreeSet<_> = document["required_env"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|item| item["name"].as_str())
        .filter(|name| !target.env_present.contains(*name))
        .collect();
    if !missing.is_empty() {
        report.note(
            "required_env_missing",
            "readiness needs configuration until these variables are set",
            json!({"names":missing.into_iter().collect::<Vec<_>>().join(", ")}),
        );
    }
    if document["requires_authorization"]
        .as_str()
        .is_some_and(|value| value != "none")
    {
        report.note(
            "authorization_required",
            "this object requires authorization after installation",
            json!({"kind":document["requires_authorization"]}),
        );
    }
    if document["requires_credentials"] == true {
        report.note(
            "credentials_required",
            "this object requires credential configuration",
            json!({"stable_id":document["stable_id"]}),
        );
    }
}
