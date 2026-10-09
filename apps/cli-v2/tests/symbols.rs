use std::{error::Error, fs};

use ai_stp_cli_v2::projects;
use serde_json::{Value, json};

fn language<'a>(report: &'a Value, name: &str) -> Result<&'a Value, Box<dyn Error>> {
    report["languages"]
        .as_array()
        .ok_or("languages")?
        .iter()
        .find(|row| row["language"] == name)
        .ok_or_else(|| "language missing".into())
}

#[test]
fn symbols_are_bounded_exact_bytes_and_explicit_about_evidence() -> Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let root = temporary.path().join("project");
    fs::create_dir_all(root.join("tests"))?;
    fs::write(
        root.join("tests/test_api.py"),
        concat!(
            "\"\"\"def Pretend():\n    pass\n\"\"\"\n",
            "@decorate\nasync def main():\n    def Nested(): pass\n",
            "class Public: pass\nclass _Private: pass\n",
            "A = B = 1\nTYPED: int = 2\n(a,b)=(1,2)\n",
            "def _hidden(): pass\nfrom . import nearby\n"
        ),
    )?;
    fs::write(
        root.join("guard.py"),
        "if '__main__' == __name__:\n    run()\n",
    )?;
    fs::write(
        root.join("false_guard.py"),
        "if __name__ != '__main__':\n    run()\n",
    )?;
    fs::write(
        root.join("main.rs"),
        "pub struct Record;\npub fn run() {}\nfn main() {}\n  pub fn Nested() {}\n",
    )?;
    fs::write(
        root.join("main.go"),
        "package main\nfunc Exported() {}\nfunc main() {}\n",
    )?;
    fs::write(
        root.join("main.ts"),
        "export const VERSION = 1;\nexport async function main() {}\n",
    )?;
    fs::write(root.join("main.js"), "export class Public {}\n")?;
    fs::write(root.join("main.dart"), "class Public {}\nvoid main() {}\n")?;
    fs::write(root.join(".env"), "TOKEN=synthetic-secret-canary")?;
    let report = projects::symbols(&root)?;
    assert_eq!(report["state"], "complete");
    let python = language(&report, "python")?;
    assert_eq!(python["method"], "syntax_tree");
    assert_eq!(python["symbols"], 5);
    assert_eq!(python["tests"], 1);
    assert_eq!(
        python["entry_points"],
        json!(["guard.py", "tests/test_api.py"])
    );
    for (name, count) in [
        ("rust", 2),
        ("go", 1),
        ("typescript", 2),
        ("javascript", 1),
        ("dart", 2),
    ] {
        let row = language(&report, name)?;
        assert_eq!(row["method"], "line_scan");
        assert_eq!(row["symbols"], count, "{name}");
        assert!(
            row["reason"]
                .as_str()
                .ok_or("reason")?
                .contains("line by line")
        );
    }
    assert_eq!(
        language(&report, "rust")?["entry_points"],
        json!(["main.rs"])
    );
    assert_eq!(language(&report, "go")?["entry_points"], json!(["main.go"]));
    assert_eq!(projects::symbols(&root)?, report);
    assert!(!serde_json::to_string(&report)?.contains("synthetic-secret-canary"));

    fs::write(root.join("invalid.py"), "def missing(:\n")?;
    let partial = projects::symbols(&root)?;
    assert_eq!(partial["state"], "partial");
    assert_eq!(language(&partial, "python")?["symbols"], 5);
    fs::write(root.join("invalid.py"), [0xff, 0xfe])?;
    assert_eq!(projects::symbols(&root)?["state"], "partial");
    fs::write(root.join("invalid.py"), vec![b' '; 512 * 1024 + 1])?;
    assert_eq!(
        projects::symbols(&root)?["stopped_by"],
        "larger than the source budget"
    );
    fs::remove_file(root.join("invalid.py"))?;
    fs::hard_link(root.join("main.rs"), root.join("alias.rs"))?;
    assert_eq!(projects::symbols(&root)?["state"], "partial");
    fs::remove_file(root.join("alias.rs"))?;
    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(temporary.path(), root.join("escape"))?;
        std::os::unix::fs::symlink("main.rs", root.join("alias.rs"))?;
        assert_eq!(projects::symbols(&root)?, report);
    }
    let deep = root.join("deep");
    let mut path = deep;
    for _ in 0..13 {
        fs::create_dir_all(&path)?;
        path = path.join("deeper");
    }
    assert_eq!(projects::symbols(&root)?["stopped_by"], "depth budget");

    let many = temporary.path().join("many");
    for bucket in 0..3 {
        let directory = many.join(bucket.to_string());
        fs::create_dir_all(&directory)?;
        for number in 0..700 {
            fs::write(
                directory.join(format!("file-{number}.py")),
                "def read(): pass\n",
            )?;
        }
    }
    let limited = projects::symbols(&many)?;
    assert_eq!(limited["stopped_by"], "file budget");
    assert_eq!(language(&limited, "python")?["files"], 2000);
    Ok(())
}
