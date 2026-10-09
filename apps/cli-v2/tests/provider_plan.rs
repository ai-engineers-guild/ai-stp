use std::{error::Error, time::Duration};

use ai_stp_cli_v2::{
    digest,
    projection::Scope,
    provider::{
        Info,
        plan::{Observed, Request},
    },
};
use serde_json::{Value, json};

fn digest_plan(value: &Value) -> Result<String, Box<dyn Error>> {
    Ok(digest::bytes(
        "ai-stp:provider-plan:v3",
        &serde_json_canonicalizer::to_vec(value)?,
    )?)
}

// Captured from the authenticated Codex 0.0.88 provider; only the portable
// destination and fixed future expiry are substituted in the retained fixture.
#[test]
fn exact_provider_plans_refuse_rehashed_foreign_inputs_and_inconsistent_echoes()
-> Result<(), Box<dyn Error>> {
    let providers: Value =
        serde_json::from_str(include_str!("fixtures/provider-declarations.json"))?;
    let provider = Info::parse(&serde_json::to_vec(&providers[1])?)?;
    let mut response: Value = serde_json::from_str(include_str!("fixtures/provider-plan.json"))?;
    let now = "2030-01-01T00:00:00Z".parse::<jiff::Timestamp>()?;
    let target = std::env::current_dir()?.join("cafe\u{301} target");
    let (os, arch) = ai_stp_cli_v2::provider::runtime::platform()?
        .split_once('/')
        .ok_or("platform")?;
    response["plan"]["canonical_target"] = json!(target);
    response["plan"]["platform"] = json!({"os":os,"arch":arch});
    response["plan_digest"] = digest_plan(&response["plan"])?.into();
    let request_value = json!({
        "operation":"install", "operation_id":response["plan"]["operation_id"],
        "expires_at":response["plan"]["expires_at"], "bundle":response["plan"]["bundle"]
    });
    let request = Request::parse(&serde_json::to_vec(&request_value)?, now)?;
    let observed = Observed {
        provider: &provider,
        release_digest: response["plan"]["provider_release_digest"]
            .as_str()
            .ok_or("release")?,
        target: &target,
        scope: Scope::Global,
        target_digest: response["plan"]["expected_target_digest"]
            .as_str()
            .ok_or("target")?,
    };
    request.planned(&serde_json::to_vec(&response)?, &observed, now)?;
    let mut validated = response["plan"]["bundle"].clone();
    validated["valid"] = true.into();
    request.validation(&serde_json::to_vec(&validated)?)?;
    for key in response["plan"]
        .as_object()
        .ok_or("plan")?
        .keys()
        .filter(|key| key.as_str() != "effects")
    {
        let mut foreign = response.clone();
        foreign["plan"][key] = "foreign".into();
        foreign["plan_digest"] = digest_plan(&foreign["plan"])?.into();
        assert!(
            request
                .planned(&serde_json::to_vec(&foreign)?, &observed, now)
                .is_err(),
            "{key}"
        );
    }
    for key in response.as_object().ok_or("response")?.keys() {
        let mut incomplete = response.clone();
        incomplete.as_object_mut().ok_or("response")?.remove(key);
        assert!(
            request
                .planned(&serde_json::to_vec(&incomplete)?, &observed, now)
                .is_err(),
            "{key}"
        );
    }
    for (key, value) in [
        ("native_capture", json!({})),
        ("target_scope", json!("project")),
        ("unknown", json!(true)),
    ] {
        let mut foreign = response.clone();
        foreign["plan"][key] = value;
        foreign["plan_digest"] = digest_plan(&foreign["plan"])?.into();
        assert!(
            request
                .planned(&serde_json::to_vec(&foreign)?, &observed, now)
                .is_err()
        );
    }
    let mut invalid_effects = response.clone();
    invalid_effects["effects"] = json!([]);
    invalid_effects["plan"]["effects"] = json!([]);
    invalid_effects["plan_digest"] = digest_plan(&invalid_effects["plan"])?.into();
    assert!(
        request
            .planned(&serde_json::to_vec(&invalid_effects)?, &observed, now)
            .is_err()
    );
    for key in [
        "bundle_format",
        "bundle_digest",
        "artifact_digest",
        "bundle_size",
        "valid",
    ] {
        let mut foreign = validated.clone();
        foreign[key] = Value::Null;
        assert!(request.validation(&serde_json::to_vec(&foreign)?).is_err());
    }
    assert!(
        request
            .validation(br#"{"valid":true,"valid":false}"#)
            .is_err()
    );
    let refused = request
        .validation(
            br#"{"state":"refused","reason":"recovery_required","detail":"private host content"}"#,
        )
        .err()
        .ok_or("refusal")?;
    let reported = serde_json::to_string(&refused.details)?;
    assert!(reported.contains("recovery_required") && !reported.contains("private host content"));
    assert!(
        request
            .check_time(now.checked_add(Duration::from_secs(900))?)
            .is_err()
    );
    for (field, value) in [
        ("operation", json!("backup")),
        ("operation_id", json!("bad")),
        ("expires_at", json!("2030-01-01T00:15:00.001Z")),
        ("unknown", json!(true)),
    ] {
        let mut invalid = request_value.clone();
        invalid[field] = value;
        assert!(Request::parse(&serde_json::to_vec(&invalid)?, now).is_err());
    }
    let payload = b"literal package bytes";
    let mut literal = request_value;
    literal["bundle"]["artifact_digest"] = digest::sha256(payload).into();
    literal["bundle"]["bundle_size"] = payload.len().into();
    let literal = Request::parse(&serde_json::to_vec(&literal)?, now)?;
    literal.check_bundle(payload, now)?;
    assert!(literal.check_bundle(b"substituted bytes", now).is_err());
    assert!(
        literal
            .check_bundle(&payload[..payload.len() - 1], now)
            .is_err()
    );
    Ok(())
}
