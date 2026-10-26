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
