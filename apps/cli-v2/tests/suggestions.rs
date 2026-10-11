use std::error::Error;

use ai_stp_cli_v2::{
    artifacts::{self, Member},
    authoring::{
        Identity,
        passports::{self, Patch},
        review,
    },
    error::{ErrorKind, Failure},
    store::{
        Store,
        revisions::{self, Write},
    },
};
use serde_json::{Value, json};

const ID: &str = "component_01ARZ3NDEKTSV4RRFFQ69G5FAV";
const AT: &str = "2026-10-09T00:00:00.000Z";

fn retain(
    store: &mut Store,
    identity: &Identity,
    files: &[(&str, &[u8])],
) -> Result<Value, Failure> {
    let members = files
        .iter()
        .map(|(path, bytes)| Member {
            path: (*path).into(),
            bytes: bytes.to_vec(),
            mode: 0o644,
        })
        .collect::<Vec<_>>();
    let bytes = artifacts::encode_tree(&members)?;
    store.transaction(|t| {
        let heads = revisions::heads(t, ID)?;
        let address = revisions::content(t, &bytes, AT)?;
        let mut facts = json!({});
        for (field, value) in [
            ("content_digest", json!(address)),
            ("content_format", json!(artifacts::TREE_FORMAT)),
            ("source_repository", json!("https://example.com/team/repo")),
            ("source_revision", json!("a".repeat(40))),
            ("source_subpath", json!("component")),
        ] {
            facts[field] =
                json!({"value":value,"origin":"observed","confirmation":"none","observed_at":AT});
        }
        revisions::commit(
            t,
            &json!({"kind":"component","stable_id":ID,"owner_id":identity.account_id,
            "created_at":AT,"parent_revision_ids":heads,"facts":facts}),
            &identity.device_id,
            None,
            Write::Advance {
                expected_heads: &heads,
            },
        )
    })
}

#[test]
fn retained_enrichment_is_exact_read_only_and_conflicts_refuse() -> Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let identity = Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    };
    let mut store = Store::open(temporary.path(), true)?;
    let package=br##"{"scripts":{"postinstall":"must-not-run"},"ai-stp":{"component":{"name":"Declared name","description":"Review changes.","permissions":{}}}}"##;
    let pyproject=b"[tool.ai-stp.component]\nname='Declared name'\ndescription='Review changes.'\n[tool.ai-stp.component.permissions]\n";
    let head = retain(
        &mut store,
        &identity,
        &[
            ("package.json", package),
            ("pyproject.toml", pyproject),
            ("nested/package.json", b"malformed ignored nested file"),
        ],
    )?;
    let output = review::suggest(&mut store, ID)?;
    assert_eq!(output["revision_id"], head["revision_id"]);
    let suggestions = output["suggestions"].as_array().ok_or("suggestions")?;
    assert_eq!(suggestions.len(), 4);
    let name = suggestions
        .iter()
        .find(|s| s["field"] == "name")
        .ok_or("name")?;
    assert_eq!(name["value"], "Declared name");
    assert_eq!(
        name["source_refs"],
        json!(["artifact:package.json", "artifact:pyproject.toml"])
    );
    assert_eq!(name["requires_confirmation"], true);
    assert!(
        output["unresolved_fields"]
            .as_array()
            .ok_or("unresolved")?
            .contains(&json!("license"))
    );
    assert_eq!(review::suggest(&mut store, ID)?, output);
    assert_eq!(
        store.transaction(|t| revisions::heads(t, ID))?,
        vec![head["revision_id"].as_str().ok_or("revision")?.to_owned()]
    );
    let plan = passports::plan(
        &mut store,
        ID,
        head["revision_id"].as_str().ok_or("revision")?,
        Patch::try_from(json!({"tags":["review"]}))?,
        identity.clone(),
        AT,
    )?;
    passports::apply(&mut store, &plan, &plan.digest()?, &identity, AT)?;
    assert!(
        !review::suggest(&mut store, ID)?["unresolved_fields"]
            .as_array()
            .ok_or("unresolved")?
            .contains(&json!("tags"))
    );
    assert_eq!(plan.passport["facts"]["name"], json!(null));

    for (files, kind) in [
        (
            vec![
                ("package.json", package.as_slice()),
                (
                    "pyproject.toml",
                    b"[tool.ai-stp.component]\nname='Conflicting name'\n".as_slice(),
                ),
            ],
            ErrorKind::Conflict,
        ),
        (
            vec![(
                "package.json",
                br#"{"ai-stp":{"component":{"invented":true}}}"#.as_slice(),
            )],
            ErrorKind::Precondition,
        ),
        (
            vec![(
                "package.json",
                br#"{"ai-stp":{"component":{"name":"one","name":"two"}}}"#.as_slice(),
            )],
            ErrorKind::Precondition,
        ),
        (
            vec![(
                "package.json",
                br#"{"ai-stp":{"component":{"permissions":{"token":"synthetic-canary"}}}}"#
                    .as_slice(),
            )],
            ErrorKind::Precondition,
        ),
        (
            vec![(
                "package.json",
                br#"{"ai-stp":{"component":null}}"#.as_slice(),
            )],
            ErrorKind::Precondition,
        ),
        (
            vec![("package.json", b"{invalid".as_slice())],
            ErrorKind::Precondition,
        ),
    ] {
        let before = retain(&mut store, &identity, &files)?;
        let error = review::suggest(&mut store, ID)
            .err()
            .ok_or("invalid declaration accepted")?;
        assert_eq!(error.kind.code(), kind.code());
        assert!(!format!("{error:?}").contains("synthetic-canary"));
        assert_eq!(
            store.transaction(|t| revisions::heads(t, ID))?,
            vec![before["revision_id"].as_str().ok_or("revision")?.to_owned()]
        );
    }
    let rich_toml=b"date=2026-10-09\n[tool.ai-stp.component]\ntags=['review']\npermissions={filesystem={read=true}, ratio=0.5}\n[[tool.ai-stp.component.runtime_requirements]]\nname='example'\n";
    // Rich values are parsed, then the closed passport schema still decides
    // whether their shape is admissible. Unrelated root dates are ignored.
    retain(&mut store, &identity, &[("pyproject.toml", rich_toml)])?;
    assert!(review::suggest(&mut store, ID).is_err());
    for invalid_toml in [
        "[tool.ai-stp.component]\nname='one'\nname='two'\n".to_owned(),
        "[tool.ai-stp.component.permissions]\nvalue=nan\n".to_owned(),
        "[tool.ai-stp.component.permissions]\nvalue=2026-10-09\n".to_owned(),
        format!(
            "[tool.ai-stp.component.permissions]\nvalue={}0{}\n",
            "[".repeat(66),
            "]".repeat(66)
        ),
    ] {
        retain(
            &mut store,
            &identity,
            &[("pyproject.toml", invalid_toml.as_bytes())],
        )?;
        assert!(review::suggest(&mut store, ID).is_err());
    }
    retain(&mut store,&identity,&[("pyproject.toml",b"date=2026-10-09\n[tool.ai-stp.component]\ntags=['review']\nrequires_credentials=false\npermissions={filesystem=['project:read']}\n")])?;
    assert_eq!(
        review::suggest(&mut store, ID)?["suggestions"]
            .as_array()
            .ok_or("suggestions")?
            .len(),
        4
    );
    retain(
        &mut store,
        &identity,
        &[("package.json", &vec![b' '; 1024 * 1024 + 1])],
    )?;
    assert!(review::suggest(&mut store, ID).is_err());
    retain(
        &mut store,
        &identity,
        &[("package.json", b"{\"name\":\"unrelated package name\"}")],
    )?;
    assert_eq!(
        review::suggest(&mut store, ID)?["suggestions"]
            .as_array()
            .ok_or("suggestions")?
            .len(),
        1
    );
    store.transaction(|t| {
        t.execute("UPDATE content SET bytes=x'00'", [])
            .map(|_| ())
            .map_err(|_| Failure::input("proof mutation"))
    })?;
    assert!(review::suggest(&mut store, ID).is_err());
    Ok(())
}
