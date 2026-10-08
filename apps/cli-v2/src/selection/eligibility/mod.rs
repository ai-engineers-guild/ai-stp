//! Deterministic decisions over exact passports and caller-established evidence.

mod checks;

use crate::{
    canonical, digest,
    error::{Failure, Result},
    harnesses, passport,
    projection::Scope,
    provider::Info,
    wire::Schema,
};
use serde::Serialize;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

static ASSESSMENT: Schema = Schema::definition(
    include_str!("../../../../../schemas/v1/cli-eligibility-report.schema.json"),
    "CandidateEligibility",
);

#[derive(Clone, Serialize)]
pub struct Target {
    pub harness_id: String,
    pub scope: Scope,
    pub os: String,
    pub arch: String,
    /// Exact observed version, not an arbitrary command-output line.
    pub harness_version: String,
    pub owner_id: String,
    pub capabilities: BTreeSet<String>,
    /// Namespaced as filesystem:value, network:value or process:value.
    pub permissions: BTreeSet<String>,
    pub entitlements: BTreeSet<String>,
    pub env_present: BTreeSet<String>,
    /// Exact object:major rights already established by the owning runtime.
    pub grants: BTreeSet<String>,
    pub pinned_passport_digests: BTreeSet<String>,
    pub for_redistribution: bool,
}

/// Established by the owning runtime, never accepted as an authentication proof.
/// The exact digest prevents applying one version's evidence to another version.
#[derive(Clone)]
pub struct Evidence {
    pub passport_digest: String,
    pub registrable: bool,
    pub blocked: bool,
    pub author_verified: bool,
    pub component_verified: bool,
    pub checks_current: bool,
    pub consented: bool,
}

pub const CAPABILITIES: &[&str] = &[
    "project.language.python",
    "project.language.typescript",
    "project.language.javascript",
    "project.language.rust",
    "project.language.go",
    "project.language.dart",
    "project.vcs.git",
    "project.surface.agents_md",
    "project.surface.claude_md",
    "project.surface.skill_md",
    "project.surface.mcp_json",
    "toolchain.ruff",
];

struct Assessment {
    refusals: Vec<Value>,
    notes: Vec<Value>,
}
impl Assessment {
    fn refuse(&mut self, family: &str, code: &str, summary: &str, details: Value) {
        self.refusals.push(json!({"schema_version":1,"family":family,"code":code,"summary":summary,"details":details}));
    }
    fn note(&mut self, code: &str, summary: &str, details: Value) {
        self.notes
            .push(json!({"schema_version":1,"code":code,"summary":summary,"details":details}));
    }
}

pub fn assess(
    document: &Value,
    target: &Target,
    evidence: &Evidence,
    provider: Option<&Info>,
) -> Result<Value> {
    passport::versions::validate_document(document)?;
    if let Some(value) = document.get("entitlements")
        && !value.as_array().is_some_and(|items| {
            items.iter().all(|item| {
                item.as_str()
                    .is_some_and(|s| !s.is_empty() && s.len() <= 1024)
            })
        })
    {
        return Err(Failure::precondition(
            "the passport entitlement extension is invalid",
        ));
    }
    if target.harness_id == "undefined"
        || (!target.owner_id.is_empty() && !passport::stable_id(&target.owner_id, "account"))
        || !matches!(target.os.as_str(), "linux" | "darwin" | "windows")
        || !matches!(target.arch.as_str(), "x86_64" | "arm64")
        || target.harness_version.len() > 128
        || target
            .harness_version
            .bytes()
            .any(|byte| !byte.is_ascii_alphanumeric() && !matches!(byte, b'.' | b'-' | b'_' | b'+'))
        || canonical::bytes(
            &serde_json::to_value(target)
                .map_err(|_| Failure::input("invalid eligibility target"))?,
        )?
        .len()
            > 256 * 1024
        || evidence.passport_digest != digest::canonical("ai-stp:passport:v1", document)?
    {
        return Err(Failure::input(
            "eligibility requires a bounded target and evidence for the exact passport",
        ));
    }
    harnesses::definition(&target.harness_id)?;
    let own = !target.owner_id.is_empty() && document["owner_id"] == target.owner_id;
    let local = own
        || target
            .pinned_passport_digests
            .contains(&evidence.passport_digest);
    let (lane, reason) = if local {
        (
            "local_owner_or_pinned",
            "your own or exactly pinned; installable after local checks".to_owned(),
        )
    } else if evidence.author_verified && evidence.component_verified && evidence.checks_current {
        (
            "authoritative",
            "confirmed author and confirmed version, checks current".to_owned(),
        )
    } else {
        let mut reasons = Vec::new();
        if !evidence.author_verified {
            reasons.push("the author is not confirmed");
        }
        if !evidence.component_verified {
            reasons.push("this version is not confirmed");
        }
        if !evidence.checks_current {
            reasons.push("mandatory checks are not current");
        }
        ("experimental", reasons.join("; "))
    };
    let mut report = Assessment {
        refusals: Vec::new(),
        notes: Vec::new(),
    };
    let scope = checks::compatibility(&mut report, document, target)?;
    let identity = json!({"stable_id":document["stable_id"]});
    if !evidence.registrable
        || document["lifecycle_state"]
            .as_str()
            .is_some_and(|state| state != "complete")
    {
        report.refuse(
            "access",
            "object_not_registrable",
            "this object is not a complete registered version",
            identity.clone(),
        );
    }
    if evidence.blocked {
        report.refuse(
            "access",
            "object_blocked",
            "a moderator has blocked this object",
            identity.clone(),
        );
    }
    let id = document["stable_id"]
        .as_str()
        .ok_or_else(|| Failure::input("missing identity"))?;
    let major = document["version"]
        .as_str()
        .and_then(|s| s.split_once('.'))
        .map(|p| p.0)
        .ok_or_else(|| Failure::input("missing version"))?;
    if !own
        && document["visibility"] != "public"
        && !target.grants.contains(&format!("{id}:{major}"))
    {
        report.refuse(
            "access",
            "grant_missing",
            "this private object is not granted on this major line",
            json!({"stable_id":id,"major":major}),
        );
    }
    if !local && !evidence.checks_current {
        report.refuse(
            "trust",
            "evidence_stale",
            "a mandatory check has no current passing evidence",
            identity.clone(),
        );
    }
    if lane == "experimental" && !evidence.consented {
        report.refuse(
            "trust",
            "unverified_without_consent",
            "no consent covers this unverified object",
            identity.clone(),
        );
    }
    let license = document["license"]["spdx_id"].as_str().unwrap_or("");
    if !own
        && (license.trim().is_empty()
            || matches!(license, "NOASSERTION" | "NONE" | "LicenseRef-Unknown"))
    {
        report.refuse(
            "license",
            "license_undeclared",
            "this object of another owner declares no usable licence",
            identity.clone(),
        );
    }
    if target.for_redistribution && document["license"]["redistribution_allowed"] != true {
        report.refuse(
            "license",
            "redistribution_forbidden",
            "the composition is for distribution but this declaration forbids it",
            json!({"stable_id":id,"license":license}),
        );
    }
    checks::permissions(&mut report, document, scope, target);
    checks::provider(&mut report, document, scope, target, provider);
    checks::notes(&mut report, document, target);
    let admissible = report.refusals.is_empty();
    let result = json!({"schema_version":1,"stable_id":document["stable_id"],"revision_id":document["revision_id"],
        "lane":lane,"lane_reason":reason,"admissible":admissible,"auto_selectable":admissible && lane != "experimental",
        "refusals":report.refusals,"notes":report.notes});
    ASSESSMENT.validate(&result)?;
    Ok(result)
}

/// Every node, including transitive members, must have exact evidence. A root's
/// trust, grant or successful assessment never stands in for its dependencies.
pub fn assess_graph(
    store: &mut crate::store::Store,
    roots: &[Value],
    target: &Target,
    evidence: &BTreeMap<String, Evidence>,
    provider: Option<&Info>,
) -> Result<Value> {
    store.transaction(|t| assess_connection(t, roots, target, evidence, provider))
}

pub(crate) fn assess_connection(
    connection: &rusqlite::Connection,
    roots: &[Value],
    target: &Target,
    evidence: &BTreeMap<String, Evidence>,
    provider: Option<&Info>,
) -> Result<Value> {
    if roots.is_empty() {
        return Err(Failure::input(
            "eligibility requires an exact component or setup root",
        ));
    }
    let graph = super::graph::exact(connection, roots)?;
    let mut assessments = Vec::new();
    if graph["resolved"] == true {
        for node in graph["nodes"]
            .as_array()
            .ok_or_else(|| Failure::precondition("graph nodes missing"))?
        {
            let id = node["stable_id"]
                .as_str()
                .ok_or_else(|| Failure::precondition("graph identity missing"))?;
            let held = evidence.get(id).ok_or_else(|| {
                Failure::precondition(
                    "an exact graph member has no established eligibility evidence",
                )
            })?;
            let document = crate::objects::Objects { connection }.exact_version(
                id,
                node["version"]
                    .as_str()
                    .ok_or_else(|| Failure::precondition("graph version missing"))?,
                Some(
                    node["passport_digest"]
                        .as_str()
                        .ok_or_else(|| Failure::precondition("graph digest missing"))?,
                ),
            )?;
            assessments.push(assess(&document, target, held, provider)?);
        }
    }
    let admissible =
        graph["resolved"] == true && assessments.iter().all(|item| item["admissible"] == true);
    let automatic = admissible
        && assessments
            .iter()
            .all(|item| item["auto_selectable"] == true);
    Ok(
        json!({"schema_version":1,"graph":graph,"assessments":assessments,"admissible":admissible,"auto_selectable":automatic}),
    )
}
