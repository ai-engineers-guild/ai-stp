use super::*;

const CORPORATE: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/packages/contracts/src/ai_stp_contracts/fixtures/v1/corporate.json"
));
const TECHNOLOGY: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/packages/contracts/src/ai_stp_contracts/fixtures/v1/technology.json"
));
const CATALOG: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/packages/contracts/src/ai_stp_contracts/fixtures/v1/catalog.json"
));
const ORGANIZATION: &str = "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
const ACCOUNT: &str = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
const CONTEXT: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/packages/contracts/src/ai_stp_contracts/fixtures/v1/context.json"
));

fn fixture(source: &str, operation: &str) -> Result<Value> {
    let source: Value = serde_json::from_str(source).map_err(|_| invalid())?;
    source["cases"]
        .as_array()
        .ok_or_else(invalid)?
        .iter()
        .find(|case| case["operation_id"] == operation && case["kind"] == "positive")
        .map(|case| case["body"].clone())
        .ok_or_else(invalid)
}

#[test]
fn unlink_readers_use_original_routes_and_reject_mixed_terminal_evidence() -> Result<()> {
    let ready = fixture(CONTEXT, "readProjectUnlinkPlanOutcome")?;
    let id = text(&ready["plan"], "plan_id")?.to_owned();
    for (request, operation, suffix) in [
        (
            Request::UnlinkOutcome {
                plan_id: id.clone(),
            },
            "readProjectUnlinkPlanOutcome",
            format!("project-unlink-plans/{id}/outcome"),
        ),
        (
            Request::UnlinkSettlement {
                plan_id: id.clone(),
            },
            "readProjectUnlinkPlanSettlement",
            format!("project-unlink-plans/{id}/settlement"),
        ),
        (
            Request::UnlinkRequestOutcome {
                request_key: "context-unlink-original-request".into(),
            },
            "readProjectUnlinkRequestOutcome",
            "project-unlink-plan-requests/context-unlink-original-request".into(),
        ),
    ] {
        let value = fixture(CONTEXT, operation)?;
        assert_eq!(request.project(&value, ORGANIZATION, ACCOUNT)?, ready);
        let (url, body) = request.wire("https://corporate.example.test", ORGANIZATION, ACCOUNT)?;
        assert_eq!(
            url.path(),
            format!("/v1/organizations/{ORGANIZATION}/{suffix}")
        );
        assert!(body.is_none() && url.query().is_none());
        let mut applied = ready.clone();
        applied["state"] = "applied".into();
        applied["link"] = fixture(CONTEXT, "readProjectLink")?;
        applied["link"]["state"] = "unlinked".into();
        applied["link"]["revision"] = 2.into();
        // The retained link's plan/digest identify the original link, not unlink.
        assert_ne!(applied["link"]["plan_id"], applied["plan"]["plan_id"]);
        assert_eq!(request.project(&applied, ORGANIZATION, ACCOUNT)?, applied);
        applied["future_private"] = "canary".into();
        applied["plan"]["future_private"] = "canary".into();
        applied["link"]["future_private"] = "canary".into();
        let projected = request.project(&applied, ORGANIZATION, ACCOUNT)?;
        assert!(!projected.to_string().contains("canary"));
        for (field, wrong) in [
            ("link_id", json!("project_link_01ARZ3NDEKTSV4RRFFQ69G5FAV")),
            (
                "organization_id",
                json!("organization_01ARZ3NDEKTSV4RRFFQ69G5FAV"),
            ),
            (
                "local_project_id",
                json!("project_01ARZ3NDEKTSV4RRFFQ69G5FAV"),
            ),
            (
                "remote_project_id",
                json!("remote_project_01ARZ3NDEKTSV4RRFFQ69G5FAV"),
            ),
            (
                "provider_project_id",
                json!("provider_project_01ARZ3NDEKTSV4RRFFQ69G5FAV"),
            ),
            ("local_revision", json!("different")),
            ("remote_revision", json!("different")),
            ("provider_revision", json!("different")),
            ("state", json!("linked")),
            ("revision", json!(3)),
        ] {
            let mut mixed = projected.clone();
            mixed["link"][field] = wrong;
            assert!(
                request.project(&mixed, ORGANIZATION, ACCOUNT).is_err(),
                "{field}"
            );
        }
        for state in ["ready", "expired"] {
            let mut wrong = projected.clone();
            wrong["state"] = state.into();
            assert!(request.project(&wrong, ORGANIZATION, ACCOUNT).is_err());
            wrong = ready.clone();
            wrong["state"] = state.into();
            assert!(request.project(&wrong, ORGANIZATION, ACCOUNT).is_ok());
        }
        let mut wrong = ready.clone();
        wrong["state"] = "applied".into();
        assert!(request.project(&wrong, ORGANIZATION, ACCOUNT).is_err());
        wrong = ready.clone();
        wrong["plan"]["organization_id"] = "organization_01ARZ3NDEKTSV4RRFFQ69G5FAV".into();
        assert!(request.project(&wrong, ORGANIZATION, ACCOUNT).is_err());
        if !matches!(request, Request::UnlinkRequestOutcome { .. }) {
            wrong = ready.clone();
            wrong["plan"]["plan_id"] = "unlink_plan_01ARZ3NDEKTSV4RRFFQ69G5FAV".into();
            assert!(request.project(&wrong, ORGANIZATION, ACCOUNT).is_err());
        }
        wrong = projected;
        wrong["plan"]["expected_link_revision"] = u64::MAX.into();
        assert!(request.project(&wrong, ORGANIZATION, ACCOUNT).is_err());
    }
    Ok(())
}

#[test]
fn unlink_reader_identifiers_cannot_select_link_plans_or_inject_routes() {
    for id in [
        "link_plan_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        "unlink_plan_short",
        "unlink_plan/unsafe",
        "unlink_plan_%2f",
    ] {
        for request in [
            Request::UnlinkOutcome { plan_id: id.into() },
            Request::UnlinkSettlement { plan_id: id.into() },
        ] {
            assert!(
                request
                    .wire("https://corporate.example.test", ORGANIZATION, ACCOUNT)
                    .is_err()
            );
        }
    }
    for key in [
        "short",
        "context/request-key",
        "context%2frequest-key",
        "context-request-key\n",
        &"k".repeat(129),
    ] {
        assert!(
            Request::UnlinkRequestOutcome {
                request_key: key.into()
            }
            .wire("https://corporate.example.test", ORGANIZATION, ACCOUNT)
            .is_err()
        );
    }
}

#[test]
fn original_link_request_keys_are_bounded_and_only_read_retained_outcomes() -> Result<()> {
    let request = Request::LinkRequestOutcome {
        request_key: "context-link-plan-0001".into(),
    };
    let value = fixture(CONTEXT, "readProjectLinkRequestOutcome")?;
    assert_eq!(
        request.project(&value, ORGANIZATION, ACCOUNT)?["state"],
        "ready"
    );
    let (url, body) = request.wire("https://corporate.example.test", ORGANIZATION, ACCOUNT)?;
    assert_eq!(
        url.path(),
        format!(
            "/v1/organizations/{ORGANIZATION}/project-link-plan-requests/context-link-plan-0001"
        )
    );
    assert!(body.is_none() && url.query().is_none());
    for key in [
        "short",
        "context/request-key",
        "context%2frequest-key",
        "context-request-key\n",
    ] {
        assert!(
            Request::LinkRequestOutcome {
                request_key: key.into()
            }
            .wire("https://corporate.example.test", ORGANIZATION, ACCOUNT)
            .is_err()
        );
    }
    Ok(())
}

#[test]
fn settlement_uses_its_explicit_barrier_route_and_exact_original_plan() -> Result<()> {
    let mut value = fixture(CONTEXT, "readProjectLinkPlanSettlement")?;
    let request = Request::LinkSettlement {
        plan_id: text(&value["plan"], "plan_id")?.into(),
    };
    let (url, body) = request.wire("https://corporate.example.test", ORGANIZATION, ACCOUNT)?;
    assert_eq!(
        url.path(),
        format!(
            "/v1/organizations/{ORGANIZATION}/project-link-plans/{}/settlement",
            text(&value["plan"], "plan_id")?
        )
    );
    assert!(body.is_none() && url.query().is_none());
    value["future_private"] = "canary".into();
    let observed = request.project(&value, ORGANIZATION, ACCOUNT)?;
    assert!(!observed.to_string().contains("canary"));
    value = observed.clone();
    value["plan"]["plan_id"] = "link_plan_01ARZ3NDEKTSV4RRFFQ69G5FAV".into();
    assert!(request.project(&value, ORGANIZATION, ACCOUNT).is_err());
    value = observed.clone();
    value["plan"]["organization_id"] = "organization_01ARZ3NDEKTSV4RRFFQ69G5FAV".into();
    assert!(request.project(&value, ORGANIZATION, ACCOUNT).is_err());
    value = observed;
    value["state"] = "applied".into();
    assert!(request.project(&value, ORGANIZATION, ACCOUNT).is_err());
    for plan_id in ["link_plan_short", "link_plan/unsafe", "link_plan_%2f"] {
        assert!(
            Request::LinkSettlement {
                plan_id: plan_id.into()
            }
            .wire("https://corporate.example.test", ORGANIZATION, ACCOUNT)
            .is_err()
        );
    }
    Ok(())
}

#[test]
fn link_outcomes_require_exact_plan_link_and_context_coordinates() -> Result<()> {
    let value = fixture(CONTEXT, "readProjectLinkPlanOutcome")?;
    let request = Request::LinkOutcome {
        plan_id: text(&value["plan"], "plan_id")?.to_owned(),
    };
    let ready = request.project(&value, ORGANIZATION, ACCOUNT)?;
    assert_eq!(ready["state"], "ready");
    let (url, body) = request.wire("https://corporate.example.test", ORGANIZATION, ACCOUNT)?;
    assert!(
        url.path()
            .ends_with(&format!("/{}/outcome", text(&value["plan"], "plan_id")?))
    );
    assert!(body.is_none() && url.query().is_none());
    let mut applied = value.clone();
    applied["state"] = "applied".into();
    applied["link"] = fixture(CONTEXT, "createProjectLink")?;
    applied["plan"]["plan_digest"] = applied["link"]["plan_digest"].clone();
    applied["future_private"] = json!({"token":"canary"});
    applied["plan"]["future_token"] = "canary".into();
    applied["link"]["future_token"] = "canary".into();
    let observed = request.project(&applied, ORGANIZATION, ACCOUNT)?;
    assert!(!observed.to_string().contains("canary"));
    for field in [
        "plan_id",
        "plan_digest",
        "organization_id",
        "local_project_id",
        "remote_project_id",
        "provider_project_id",
    ] {
        let mut wrong = observed.clone();
        wrong["link"][field] = Value::Null;
        if field == "provider_project_id" {
            wrong["link"][field] = "provider_project_01ARZ3NDEKTSV4RRFFQ69G5FAV".into();
        }
        assert!(
            request.project(&wrong, ORGANIZATION, ACCOUNT).is_err(),
            "{field}"
        );
    }
    let mut wrong = value.clone();
    wrong["state"] = "applied".into();
    assert!(request.project(&wrong, ORGANIZATION, ACCOUNT).is_err());
    wrong = observed;
    wrong["state"] = "ready".into();
    assert!(request.project(&wrong, ORGANIZATION, ACCOUNT).is_err());
    wrong = value;
    wrong["plan"]["organization_id"] = "organization_01ARZ3NDEKTSV4RRFFQ69G5FAV".into();
    assert!(request.project(&wrong, ORGANIZATION, ACCOUNT).is_err());
    Ok(())
}

#[test]
fn link_targets_drop_extensions_and_refuse_mixed_or_duplicate_coordinates() -> Result<()> {
    let project = "remote_project_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
    let request = Request::LinkTarget {
        project_id: project.into(),
    };
    let provider = json!({"provider_project_id":"provider_project_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        "provider":"github","immutable_repository_id":"123456","revision":7,"future_token":"canary"});
    let mut value = json!({"schema_version":1,"organization_id":ORGANIZATION,"remote_project_id":project,
        "remote_revision":"initial","authorization_revision":format!("corporate:{ORGANIZATION}:1:1"),
        "providers":[provider.clone()],"observed_at":"2026-10-25T00:00:00.000Z","observation_only":true,
        "future_private":{"credential":"canary"}});
    let observed = request.project(&value, ORGANIZATION, ACCOUNT)?;
    assert!(!observed.to_string().contains("canary"));
    let (url, body) = request.wire("https://corporate.example.test", ORGANIZATION, ACCOUNT)?;
    assert_eq!(
        url.path(),
        format!("/v1/organizations/{ORGANIZATION}/project-link-targets/{project}")
    );
    assert!(body.is_none() && url.query().is_none());
    value["providers"] = json!([provider.clone(), provider]);
    assert!(request.project(&value, ORGANIZATION, ACCOUNT).is_err());
    value = observed.clone();
    value["remote_project_id"] = "remote_project_01ARZ3NDEKTSV4RRFFQ69G5FAV".into();
    assert!(request.project(&value, ORGANIZATION, ACCOUNT).is_err());
    value = observed.clone();
    value["organization_id"] = "organization_01ARZ3NDEKTSV4RRFFQ69G5FAV".into();
    assert!(request.project(&value, ORGANIZATION, ACCOUNT).is_err());
    value = observed;
    value["remote_revision"] = "sha256:short".into();
    assert!(request.project(&value, ORGANIZATION, ACCOUNT).is_err());
    Ok(())
}

#[test]
fn actual_contract_corpus_keeps_corporate_coordinates_and_drops_extensions() -> Result<()> {
    let cases = [
        (Request::Teams, fixture(CORPORATE, "listCorporateTeams")?),
        (
            Request::Projects {
                membership_only: false,
            },
            fixture(CORPORATE, "listCorporateProjects")?,
        ),
        (
            Request::Project {
                project_id: "remote_project_01JQZK7B8N4M6P2R9T5V0X3Y7Z".into(),
            },
            fixture(CORPORATE, "readCorporateProject")?,
        ),
        (
            Request::Technologies {
                query: None,
                offset: 0,
            },
            fixture(TECHNOLOGY, "listTechnologies")?,
        ),
        (
            Request::Mappings,
            fixture(TECHNOLOGY, "listTechnologyMappings")?,
        ),
        (
            Request::Mapping {
                version: "v1".into(),
            },
            fixture(TECHNOLOGY, "readTechnologyMapping")?,
        ),
        (
            Request::Catalog {
                object_kind: ObjectKind::Component,
                query: None,
                harness: None,
                cursor: None,
            },
            fixture(CATALOG, "searchComponents")?,
        ),
        (
            Request::Catalog {
                object_kind: ObjectKind::Setup,
                query: None,
                harness: None,
                cursor: None,
            },
            fixture(CATALOG, "searchSetups")?,
        ),
        (
            Request::AssignmentPreview {
                harness: "claude-code".into(),
                project_id: Some("remote_project_01JQZK7B8N4M6P2R9T5V0X3Y7Z".into()),
                technology_id: None,
            },
            fixture(CORPORATE, "planCorporateAssignment")?,
        ),
    ];
    for (request, mut value) in cases {
        value["future_token"] = "canary".into();
        if let Some(item) = value["items"]
            .as_array_mut()
            .and_then(|items| items.first_mut())
        {
            item["future_token"] = "canary".into();
        }
        let observed = request.project(&value, ORGANIZATION, ACCOUNT)?;
        assert!(
            !observed.to_string().contains("canary"),
            "{}",
            serde_json::to_string(&request).map_err(|_| invalid())?
        );
        let (url, body) = request.wire("https://corporate.example.test", ORGANIZATION, ACCOUNT)?;
        assert_eq!(
            url.origin().ascii_serialization(),
            "https://corporate.example.test"
        );
        assert_eq!(
            body.is_some(),
            matches!(request, Request::AssignmentPreview { .. })
        );
        assert!(
            !url.as_str().contains(ACCOUNT)
                || matches!(
                    request,
                    Request::Projects {
                        membership_only: true
                    }
                )
        );
    }
    Ok(())
}

#[test]
fn populated_team_pages_follow_the_servers_opaque_identity_contract() -> Result<()> {
    let team = fixture(CORPORATE, "readCorporateTeam")?;
    let mut page = json!({"schema_version":1,"items":[team]});
    let projected = Request::Teams.project(&page, ORGANIZATION, ACCOUNT)?;
    assert_eq!(
        projected["items"][0]["team_id"],
        page["items"][0]["team_id"]
    );
    page["items"][0]["team_id"] = "external-team-identifier".into();
    Request::Teams.project(&page, ORGANIZATION, ACCOUNT)?;
    for invalid_id in [String::new(), "x".repeat(129), "team\nidentity".into()] {
        page["items"][0]["team_id"] = invalid_id.into();
        assert!(
            Request::Teams
                .project(&page, ORGANIZATION, ACCOUNT)
                .is_err()
        );
    }
    page["items"][0]["team_id"] = "opaque-team".into();
    let duplicate = page["items"][0].clone();
    page["items"]
        .as_array_mut()
        .ok_or_else(invalid)?
        .push(duplicate);
    assert!(
        Request::Teams
            .project(&page, ORGANIZATION, ACCOUNT)
            .is_err()
    );
    page["items"].as_array_mut().ok_or_else(invalid)?.pop();
    page["items"][0]["organization_id"] = "organization_01ARZ3NDEKTSV4RRFFQ69G5FAV".into();
    assert!(
        Request::Teams
            .project(&page, ORGANIZATION, ACCOUNT)
            .is_err()
    );
    Ok(())
}

#[test]
fn every_initial_harness_uses_the_current_account_and_no_mixed_installation_inventory() -> Result<()>
{
    for target in [
        "codex",
        "claude-code",
        "antigravity",
        "grok-build",
        "cursor",
        "opencode",
        "pi",
    ] {
        let request = Request::AssignmentPreview {
            harness: target.into(),
            project_id: None,
            technology_id: None,
        };
        let (url, body) = request.wire("https://corporate.example.test", ORGANIZATION, ACCOUNT)?;
        assert!(url.path().ends_with("/catalog-assignments/plan"));
        let body = body.ok_or_else(invalid)?;
        assert_eq!(body["account_id"], ACCOUNT);
        assert_eq!(body["harness"], target);
        assert_eq!(body["materialized"], json!([]));
    }
    assert!(
        Request::Mapping {
            version: "..".into()
        }
        .validate()
        .is_err()
    );
    assert!(
        Request::Project {
            project_id: "project_01JQZK7B8N4M6P2R9T5V0X3Y7Z".into()
        }
        .validate()
        .is_err()
    );
    assert!(
        Request::AssignmentPreview {
            harness: "undefined".into(),
            project_id: None,
            technology_id: None
        }
        .validate()
        .is_err()
    );
    let mut body = fixture(CORPORATE, "planCorporateAssignment")?;
    let request = Request::AssignmentPreview {
        harness: "claude-code".into(),
        project_id: Some("remote_project_01JQZK7B8N4M6P2R9T5V0X3Y7Z".into()),
        technology_id: None,
    };
    body["account_id"] = "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into();
    assert!(request.project(&body, ORGANIZATION, ACCOUNT).is_err());
    Ok(())
}
