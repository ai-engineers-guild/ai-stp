use ai_stp_cli_v2::{
    digest, passport,
    projection::Scope,
    provider::Info,
    selection::eligibility::{self, Evidence, Target},
    store::revisions,
};
use serde_json::{Value, json};
use std::{collections::BTreeSet, error::Error};

fn facts(document: &Value) -> Result<Evidence, Box<dyn Error>> {
    Ok(Evidence {
        passport_digest: digest::canonical("ai-stp:passport:v1", document)?,
        registrable: true,
        blocked: false,
        author_verified: false,
        component_verified: false,
        checks_current: false,
        consented: false,
    })
}
fn seal(mut document: Value) -> Result<Value, Box<dyn Error>> {
    document["adaptations"][0] = passport::versions::seal_adaptation(&document["adaptations"][0])?;
    Ok(revisions::seal(&document)?)
}
fn codes(report: &Value) -> BTreeSet<&str> {
    report["refusals"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|item| item["code"].as_str())
        .collect()
}
fn reassess(document: Value, target: &Target, provider: &Info) -> Result<Value, Box<dyn Error>> {
    let document = seal(document)?;
    Ok(eligibility::assess(
        &document,
        target,
        &facts(&document)?,
        Some(provider),
    )?)
}

#[test]
fn actual_passport_scopes_and_provider_profiles_control_eligibility() -> Result<(), Box<dyn Error>>
{
    // Public declaration captured from claude-setup-system 0.0.88; no invocation
    // or package provenance is inferred merely from accepting these bytes.
    let declarations: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/provider-declarations.json"))?;
    let original = declarations
        .iter()
        .find(|value| value["harness_id"] == "claude-code")
        .ok_or("Claude declaration missing")?;
    for declaration in &declarations {
        Info::parse(&serde_json::to_vec(declaration)?)?;
    }
    let provider = Info::parse(&serde_json::to_vec(original)?)?;
    assert!(provider.profile(Scope::Project).is_some());
    assert!(provider.profile(Scope::UserRoot).is_none());
    for case in [
        "digest",
        "command",
        "operation",
        "launch",
        "duplicate_scope",
    ] {
        let mut bad = original.clone();
        match case {
            "digest" => bad["projection_profile"]["max_files"] = 2.into(),
            "command" => {
                bad["supported_commands"]
                    .as_array_mut()
                    .ok_or("commands missing")?
                    .retain(|v| v != "status");
            }
            "operation" => {
                bad["supported_operations"]
                    .as_array_mut()
                    .ok_or("operations missing")?
                    .retain(|v| v != "replace");
            }
            "launch" => {
                bad["supported_commands"]
                    .as_array_mut()
                    .ok_or("commands missing")?
                    .retain(|v| v != "launch");
            }
            _ => {
                let mut duplicate = bad["scoped_projection_profiles"][0].clone();
                duplicate["profile_id"] = "different".into();
                let mut payload = duplicate.clone();
                payload
                    .as_object_mut()
                    .ok_or("profile missing")?
                    .remove("digest");
                duplicate["digest"] =
                    digest::canonical("ai-stp:provider-projection:v3", &payload)?.into();
                bad["scoped_projection_profiles"]
                    .as_array_mut()
                    .ok_or("profiles missing")?
                    .push(duplicate);
            }
        }
        assert!(
            Info::parse(&serde_json::to_vec(&bad)?).is_err(),
            "accepted {case}"
        );
    }
    let mut legacy_request = original.clone();
    legacy_request["plan_request_fields"] = json!([]);
    let legacy_request = Info::parse(&serde_json::to_vec(&legacy_request)?)?;
    assert!(legacy_request.profile(Scope::Project).is_some());
    assert!(!legacy_request.supports_target(Scope::Project));
    assert!(legacy_request.supports_target(Scope::Global));
    let catalog: Value = serde_json::from_str(include_str!(
        "../../../packages/contracts/src/ai_stp_contracts/fixtures/v1/catalog.json"
    ))?;
    let mut document = catalog["cases"]
        .as_array()
        .ok_or("cases missing")?
        .iter()
        .find(|case| case["case_id"] == "readComponentVersion.published")
        .ok_or("fixture missing")?["body"]["passport"]
        .clone();
    document["requires_capabilities"] = json!(["project.language.rust"]);
    document["required_env"] = json!([{"name":"APP_PROFILE","purpose":"Select project"}]);
    document["requires_credentials"] = true.into();
    document["requires_authorization"] = "user_account".into();
    document["permissions"] = json!({"filesystem":["read:project"],"network":[],"process":[]});
    document["entitlements"] = json!(["workspace-tools"]);
    let scope = &mut document["adaptations"][0]["scope_adaptations"][0];
    scope["required_surface"] = json!({"profile_id":original["projection_profile"]["profile_id"],"profile_digest":original["projection_profile"]["digest"],"bundle_format":"ai-stp-bundle/2"});
    scope["members"][0]["path"] = "skills/example/SKILL.md".into();
    scope["supported_os"] = json!(["linux"]);
    scope["supported_arch"] = json!(["x86_64"]);
    scope["supported_harness_versions"] = json!(["2.1.224"]);
    scope["permissions"] = json!({"filesystem":[],"network":["https:example.com"],"process":[]});
    let document = seal(document)?;
    let target = Target {
        harness_id: "claude-code".into(),
        scope: Scope::Global,
        os: "linux".into(),
        arch: "x86_64".into(),
        harness_version: "2.1.224".into(),
        owner_id: document["owner_id"].as_str().ok_or("owner missing")?.into(),
        capabilities: ["project.language.rust".into()].into(),
        permissions: [
            "filesystem:read:project".into(),
            "network:https:example.com".into(),
        ]
        .into(),
        entitlements: ["workspace-tools".into()].into(),
        env_present: BTreeSet::new(),
        grants: BTreeSet::new(),
        pinned_passport_digests: BTreeSet::new(),
        for_redistribution: false,
    };
    let report = eligibility::assess(&document, &target, &facts(&document)?, Some(&provider))?;
    assert_eq!(report["admissible"], true);
    assert_eq!(report["auto_selectable"], true);
    assert_eq!(report["lane"], "local_owner_or_pinned");
    assert_eq!(report["notes"].as_array().ok_or("notes missing")?.len(), 3);
    for (field, value, expected) in [
        ("supported_os", json!(["windows"]), "os_unsupported"),
        ("supported_arch", json!(["arm64"]), "arch_unsupported"),
        (
            "supported_harness_versions",
            json!([">=1"]),
            "harness_version_unsupported",
        ),
        (
            "technical_support",
            json!("unsupported"),
            "adaptation_unavailable",
        ),
    ] {
        let mut changed = document.clone();
        changed["adaptations"][0]["scope_adaptations"][0][field] = value;
        assert!(
            codes(&reassess(changed, &target, &provider)?).contains(expected),
            "scope lost {field}"
        );
    }
    let mut unknown = target.clone();
    unknown.harness_version.clear();
    assert!(
        codes(&eligibility::assess(
            &document,
            &unknown,
            &facts(&document)?,
            Some(&provider)
        )?)
        .contains("harness_version_unknown")
    );
    let mut project = target.clone();
    project.scope = Scope::Project;
    assert!(
        codes(&eligibility::assess(
            &document,
            &project,
            &facts(&document)?,
            Some(&provider)
        )?)
        .contains("adaptation_unavailable")
    );
    let mut denied = target.clone();
    denied.capabilities.clear();
    denied.permissions.clear();
    denied.entitlements.clear();
    let report = eligibility::assess(&document, &denied, &facts(&document)?, Some(&provider))?;
    assert_eq!(
        codes(&report),
        ["capability_missing", "entitlement_not_granted"].into()
    );
    assert_eq!(
        report["refusals"]
            .as_array()
            .ok_or("refusals missing")?
            .len(),
        4
    );
    let mut changed = document.clone();
    changed["adaptations"][0]["scope_adaptations"][0]["members"][0]["path"] =
        "skills-backdoor/run".into();
    assert!(
        codes(&reassess(changed, &target, &provider)?).contains("provider_surface_unavailable")
    );
    let mut changed = document.clone();
    changed["adaptations"][0]["scope_adaptations"][0]["required_surface"]["profile_digest"] =
        digest::sha256(b"substitution").into();
    assert!(
        codes(&reassess(changed, &target, &provider)?).contains("provider_surface_unavailable")
    );
    assert!(
        codes(&eligibility::assess(
            &document,
            &target,
            &facts(&document)?,
            None
        )?)
        .contains("provider_unavailable")
    );
    let mut another = target.clone();
    another.owner_id = "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into();
    assert_ne!(document["owner_id"], another.owner_id);
    let mut evidence = facts(&document)?;
    let report = eligibility::assess(&document, &another, &evidence, Some(&provider))?;
    assert!(codes(&report).contains("evidence_stale"));
    assert!(codes(&report).contains("unverified_without_consent"));
    evidence.checks_current = true;
    evidence.consented = true;
    let report = eligibility::assess(&document, &another, &evidence, Some(&provider))?;
    assert_eq!(report["admissible"], true);
    assert_eq!(report["auto_selectable"], false);
    evidence.author_verified = true;
    assert_eq!(
        eligibility::assess(&document, &another, &evidence, Some(&provider))?["lane"],
        "experimental"
    );
    evidence.component_verified = true;
    assert_eq!(
        eligibility::assess(&document, &another, &evidence, Some(&provider))?["auto_selectable"],
        true
    );
    let mut private = document.clone();
    private["visibility"] = "private".into();
    private = seal(private)?;
    let evidence = facts(&private)?;
    another
        .pinned_passport_digests
        .insert(evidence.passport_digest.clone());
    assert_eq!(
        codes(&eligibility::assess(
            &private,
            &another,
            &evidence,
            Some(&provider)
        )?),
        ["grant_missing"].into()
    );
    another.grants.insert(format!(
        "{}:1",
        private["stable_id"].as_str().ok_or("id missing")?
    ));
    assert_eq!(
        eligibility::assess(&private, &another, &evidence, Some(&provider))?["admissible"],
        true
    );
    let mut changed = document.clone();
    changed["license"]["redistribution_allowed"] = false.into();
    let mut redistribution = target.clone();
    redistribution.for_redistribution = true;
    assert!(
        codes(&reassess(changed, &redistribution, &provider)?).contains("redistribution_forbidden")
    );
    let mut changed = document.clone();
    changed["entitlements"] = true.into();
    changed = seal(changed)?;
    assert!(eligibility::assess(&changed, &target, &facts(&changed)?, Some(&provider)).is_err());
    let mut wrong = facts(&document)?;
    wrong.passport_digest = digest::sha256(b"other-version");
    assert!(eligibility::assess(&document, &target, &wrong, Some(&provider)).is_err());
    Ok(())
}
