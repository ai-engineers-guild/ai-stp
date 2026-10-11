use std::error::Error;

use ai_stp_cli_v2::authoring::contribution::{self, Format};

#[test]
fn owned_contributions_round_trip_without_changing_unowned_configuration()
-> Result<(), Box<dyn Error>> {
    let toml = b"# User preference\nmodel = 'example' # retained\nstarted = 2026-10-08T00:00:00Z\n\n[mcp_servers.example]\ncommand = 'server'\nargs = ['--literal']\n\n[unowned]\nkeep = 'exact' # untouched\n";
    let component = contribution::extract(Format::Toml, toml, "mcp_servers")?;
    let parsed: toml_edit::DocumentMut = std::str::from_utf8(&component)?.parse()?;
    assert!(parsed.contains_key("example"));
    assert!(!parsed.contains_key("mcp_servers"));
    assert!(!parsed.contains_key("model"));
    let assembled = contribution::assemble(Format::Toml, Some(toml), "mcp_servers", &component)?;
    let rendered = std::str::from_utf8(&assembled)?;
    assert!(rendered.contains("# User preference\nmodel = 'example' # retained"));
    assert!(rendered.contains("started = 2026-10-08T00:00:00Z"));
    assert!(rendered.contains("[unowned]\nkeep = 'exact' # untouched"));
    let restored: toml_edit::DocumentMut = rendered.parse()?;
    assert_eq!(restored["unowned"]["keep"].as_str(), Some("exact"));
    assert_eq!(
        contribution::extract(Format::Toml, &assembled, "mcp_servers")?,
        component
    );
    assert_eq!(
        contribution::assemble(Format::Toml, Some(&assembled), "mcp_servers", &component)?,
        assembled
    );
    let inline = contribution::extract(
        Format::Toml,
        b"mcp_servers = { example = { command = 'server' } }",
        "mcp_servers",
    )?;
    assert!(contribution::has_entries(
        Format::Toml,
        &contribution::assemble(Format::Toml, None, "mcp_servers", &inline)?,
        "mcp_servers"
    )?);

    let jsonc = "{\n  // User preference\n  \"model\": \"example\", // retained\n  \"large\": 9007199254740993,\n  \"mcp\": {\"example\": {\"command\": \"server\", \"id\": 9007199254740993, \"label\": \"e\u{301}\",},},\n}\n";
    let component = contribution::extract(Format::Jsonc, jsonc.as_bytes(), "mcp")?;
    let value: serde_json::Value = serde_json::from_slice(&component)?;
    assert!(value.get("mcp").is_none());
    assert_eq!(value["example"]["id"].as_u64(), Some(9_007_199_254_740_993));
    assert_eq!(value["example"]["label"], "e\u{301}");
    let assembled =
        contribution::assemble(Format::Jsonc, Some(jsonc.as_bytes()), "mcp", &component)?;
    let rendered = std::str::from_utf8(&assembled)?;
    assert!(rendered.contains("// User preference"));
    assert!(rendered.contains("// retained"));
    assert!(rendered.contains("\"large\": 9007199254740993"));
    assert_eq!(
        contribution::extract(Format::Jsonc, &assembled, "mcp")?,
        component
    );
    assert_eq!(
        contribution::assemble(Format::Jsonc, Some(&assembled), "mcp", &component)?,
        assembled
    );
    let json = contribution::assemble(Format::Json, None, "mcp", &component)?;
    assert!(contribution::has_entries(Format::Json, &json, "mcp")?);
    assert_eq!(
        contribution::extract(Format::Json, &json, "mcp")?,
        component
    );

    for invalid in [
        r#"{"mcp":{},"mcp":{}}"#,
        r#"{"mcp":{},"\u006dcp":{}}"#,
        r#"{"mcp":{"a":1,"a":2}}"#,
        r#"{mcp:{}}"#,
        r#"{'mcp':{}}"#,
        r#"{"mcp":{"value":NaN}}"#,
        r#"{"mcp":{"value":0x10}}"#,
        r#"{"mcp":{"value":+1}}"#,
        r#"{"mcp":{"value":.1}}"#,
        r#"{"mcp":{"a":1 "b":2}}"#,
        r#"{"mcp":"\x41"}"#,
    ] {
        assert!(contribution::extract(Format::Jsonc, invalid.as_bytes(), "mcp").is_err());
    }
    for invalid in [r#"{"mcp":{},}"#, "{\n// comment\n\"mcp\":{}}"] {
        assert!(contribution::extract(Format::Json, invalid.as_bytes(), "mcp").is_err());
    }
    assert!(contribution::extract(Format::Toml, b"mcp_servers = 1", "mcp_servers").is_err());
    assert!(
        contribution::extract(
            Format::Toml,
            b"mcp_servers = {}\nmcp_servers = {}",
            "mcp_servers"
        )
        .is_err()
    );
    assert!(!contribution::has_entries(Format::Json, b"{}", "mcp")?);
    assert!(!contribution::has_entries(
        Format::Toml,
        b"mcp_servers = {}",
        "mcp_servers"
    )?);
    let empty = contribution::assemble(Format::Toml, None, "mcp_servers", b"")?;
    assert_eq!(
        contribution::extract(Format::Toml, &empty, "mcp_servers")?,
        b""
    );
    for value in [b"null".as_slice(), b"[]", b"1", b"\"text\""] {
        assert!(contribution::assemble(Format::Json, None, "mcp", value).is_err());
    }
    assert!(contribution::extract(Format::Json, &vec![b' '; 4 * 1024 * 1024 + 1], "mcp").is_err());
    let deep = format!("{{\"mcp\":{}0{}}}", "[".repeat(130), "]".repeat(130));
    assert!(contribution::extract(Format::Json, deep.as_bytes(), "mcp").is_err());
    Ok(())
}
