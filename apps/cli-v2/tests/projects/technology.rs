use ai_stp_cli_v2::{digest, projects::technology};
use serde_json::{Value, json};
use std::{error::Error, fs};

fn finding<'a>(
    report: &'a Value,
    kind: &str,
    name: &str,
    context: &str,
) -> Result<&'a Value, Box<dyn Error>> {
    report["findings"]
        .as_array()
        .ok_or("findings")?
        .iter()
        .find(|r| r["kind"] == kind && r["coordinate"] == name && r["context"] == context)
        .ok_or_else(|| format!("missing {kind}:{name}:{context}").into())
}

pub fn prove() -> Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let fixtures = [
        (
            "pyproject.toml",
            concat!(
                "[project]\nrequires-python = '>=3.12'\ndependencies = ['Django>=5', 'Private_Name @ https://user:synthetic-canary@example.invalid/pkg']\n",
                "[dependency-groups]\ntest = ['pytest>=8']\ndev = [{ include-group = 'test' }]\n"
            ),
        ),
        (
            "package.json",
            r#"{"dependencies":{"react":"^19","unknown-native-fixture":"1.0"},"devDependencies":{"typescript":"~5"},"engines":{"node":">=22"},"scripts":{"postinstall":"touch must-not-exist"}}"#,
        ),
        (
            "Cargo.toml",
            "[package]\nname='fixture'\nrust-version='1.99'\n[dependencies]\nserde_alias={ package='serde', version='1' }\n[target.'cfg(windows)'.dev-dependencies]\nwin-test='2'\n[workspace.dependencies]\nunused='3'\n",
        ),
        (
            "Cargo.lock",
            "version=4\n[[package]]\nname='serde'\nversion='1.0.0'\n",
        ),
        (
            "package-lock.json",
            r#"{"lockfileVersion":3,"packages":{"node_modules/react":{"version":"19.1.0"}}}"#,
        ),
        (
            "go.mod",
            "module example.invalid/project\ngo 1.26\nrequire github.com/stretchr/testify v1.10.0\n",
        ),
        (
            "go.sum",
            "github.com/stretchr/testify v1.9.0/go.mod h1:synthetic\n",
        ),
        (
            "compose.yaml",
            "services:\n  db:\n    image: docker.io/library/postgres:18\n",
        ),
        (
            "Dockerfile",
            "FROM alpine:3.22 AS build\nRUN touch must-not-exist\nFROM build AS final\n",
        ),
        (
            "pubspec.yaml",
            "environment:\n  sdk: '>=3.6'\ndependencies:\n  flutter:\n    sdk: flutter\n",
        ),
        ("pubspec.lock", "packages:\n  http:\n    version: '1.4.0'\n"),
        (
            "pnpm-lock.yaml",
            "lockfileVersion: '9.0'\npackages:\n  '@types/node@22.0.0': {}\n",
        ),
        (
            "yarn.lock",
            "__metadata:\n  version: 8\n'lodash@npm:^4.17.0':\n  version: 4.17.21\n",
        ),
        (
            "setup.cfg",
            "[options]\ninstall_requires =\n    Flask>=3\n[options.extras_require]\ntest =\n    coverage>=7\n",
        ),
        (".tool-versions", "node 22.0.0 24.0.0\n"),
        ("main.rs", "fn main() {}\n"),
        (".env", "TOKEN=synthetic-canary\n"),
    ];
    for (name, body) in fixtures {
        fs::write(root.path().join(name), body)?;
    }
    let first = technology::inspect(root.path())?;
    assert_eq!(first["state"], "complete", "{first}");
    assert_eq!(technology::inspect(root.path())?, first);
    assert_eq!(first["execution"], "not_run");
    assert_eq!(first["installed_software_verified"], false);
    assert!(!root.path().join("must-not-exist").exists());
    assert!(!first.to_string().contains("synthetic-canary"));
    assert!(!first.to_string().contains("https://user"));
    assert!(finding(&first, "package", "react", "production")?["technology_id"].is_string());
    assert!(
        finding(&first, "package", "unknown-native-fixture", "production")?["technology_id"]
            .is_null()
    );
    for (kind, name, context, wanted, version_kind) in [
        ("package", "django", "production", ">=5", "declared_range"),
        ("package", "pytest", "testing", ">=8", "declared_range"),
        ("package", "coverage", "testing", ">=7", "declared_range"),
        ("package", "serde", "production", "1", "declared_range"),
        ("package", "serde", "unspecified", "1.0.0", "locked_version"),
        (
            "package",
            "react",
            "unspecified",
            "19.1.0",
            "locked_version",
        ),
        (
            "package",
            "@types/node",
            "unspecified",
            "22.0.0",
            "locked_version",
        ),
        (
            "package",
            "lodash",
            "unspecified",
            "4.17.21",
            "locked_version",
        ),
        (
            "package",
            "github.com/stretchr/testify",
            "unspecified",
            "v1.9.0",
            "recorded_version",
        ),
        ("image", "postgres", "production", "18", "declared_range"),
    ] {
        let row = finding(&first, kind, name, context)?;
        assert!(
            row["claims"]
                .as_array()
                .ok_or("claims")?
                .iter()
                .any(|c| c["version"] == wanted && c["version_kind"] == version_kind),
            "{row}"
        );
    }
    assert!(finding(&first, "image", "build", "production").is_err());
    assert!(
        finding(&first, "package", "private-name", "production")?["claims"][0]["version"].is_null()
    );
    for row in first["findings"].as_array().ok_or("findings")? {
        for claim in row["claims"].as_array().ok_or("claims")? {
            for trace in claim["evidence"].as_array().ok_or("evidence")? {
                let bytes = fs::read(root.path().join(trace["path"].as_str().ok_or("path")?))?;
                assert_eq!(trace["digest"], digest::sha256(&bytes));
            }
        }
    }
    for (name, body) in fixtures {
        assert_eq!(fs::read(root.path().join(name))?, body.as_bytes());
    }
    fs::write(
        root.path().join("package.json"),
        "{\"dependencies\":{},\"dependencies\":{\"forged\":\"1\"}}",
    )?;
    let partial = technology::inspect(root.path())?;
    assert_eq!(partial["state"], "partial");
    assert!(!partial.to_string().contains("forged"));
    fs::write(
        root.path().join("package.json"),
        r#"{"dependencies":["react"]}"#,
    )?;
    assert_eq!(technology::inspect(root.path())?["state"], "partial");
    fs::write(root.path().join("package.json"), fixtures[1].1)?;
    for invalid in [
        "services: [",
        "services: {db: {<<: {image: leaked}}}",
        "services: &secret {x: {image: leaked}}\nother: *secret",
        "services:\n  x: {image: one, image: leaked}",
    ] {
        fs::write(root.path().join("compose.yaml"), invalid)?;
        let partial = technology::inspect(root.path())?;
        assert_eq!(partial["state"], "partial");
        assert!(!partial.to_string().contains("leaked"));
    }
    fs::write(
        root.path().join("compose.yaml"),
        "services:\n  db:\n    image: '${PRIVATE_IMAGE}'\n",
    )?;
    assert_eq!(
        technology::inspect(root.path())?["stopped_by"],
        "dynamic image reference"
    );
    fs::write(
        root.path().join("compose.yaml"),
        "services:\n  db:\n    image: 'user:synthetic-canary@registry.invalid/image'\n",
    )?;
    let credentials = technology::inspect(root.path())?;
    assert_eq!(credentials["state"], "partial");
    assert!(!credentials.to_string().contains("synthetic-canary"));
    fs::write(root.path().join("compose.yaml"), fixtures[7].1)?;
    fs::write(root.path().join("requirements.txt"), "-r ../outside.txt\n")?;
    assert_eq!(technology::inspect(root.path())?["state"], "partial");
    fs::remove_file(root.path().join("requirements.txt"))?;
    let previous = technology::inspect(root.path())?;
    fs::write(
        root.path().join("Cargo.lock"),
        "version=4\n[[package]]\nname='serde'\nversion='2.0.0'\n",
    )?;
    assert_ne!(
        technology::inspect(root.path())?["index_digest"],
        previous["index_digest"]
    );
    fs::write(root.path().join("Cargo.lock"), vec![b' '; 1024 * 1024 + 1])?;
    assert_eq!(technology::inspect(root.path())?["state"], "partial");
    fs::write(root.path().join("Cargo.lock"), [0, 1])?;
    assert_eq!(technology::inspect(root.path())?["state"], "partial");
    fs::write(root.path().join("Cargo.lock"), fixtures[3].1)?;
    fs::write(
        root.path().join("package.json"),
        serde_json::to_vec(
            &json!({"dependencies":(0..4097).map(|n|(format!("fixture-{n}"),"1")).collect::<std::collections::BTreeMap<_,_>>()}),
        )?,
    )?;
    assert_eq!(technology::inspect(root.path())?["state"], "partial");
    Ok(())
}
