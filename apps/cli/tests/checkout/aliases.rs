//! Real OS aliases must retain one passport and cannot authorize a replaced root.

use super::*;
use ai_stp_cli::{authoring::Identity, error::Failure, projects::passports, store::Store};

fn counts(store: &mut Store) -> Result<[i64; 3], Box<dyn Error>> {
    Ok(store.transaction(|t| {
        t.query_row(
            "SELECT (SELECT count(*) FROM project_root),(SELECT count(*) FROM entity WHERE kind='project'),(SELECT count(*) FROM operation)",
            [], |r| Ok([r.get(0)?, r.get(1)?, r.get(2)?]),
        ).map_err(|_| Failure::precondition("fixture registry counts"))
    })?)
}

#[test]
fn physical_aliases_keep_one_project_and_refuse_a_replaced_registered_root()
-> Result<(), Box<dyn Error>> {
    let temp = tempfile::tempdir()?;
    let state = temp.path().join("state");
    let name = if cfg!(target_os = "macos") {
        "Checkout-café"
    } else {
        "Checkout"
    };
    let root = temp.path().join(name);
    let neighbor = temp.path().join("Neighbor");
    fs::create_dir(&state)?;
    for path in [&root, &neighbor] {
        fs::create_dir(path)?;
        fs::write(path.join("main.rs"), b"fn main() {}\n")?;
        command(path, &["init", "--initial-branch=main"])?;
        command(path, &["commit", "--allow-empty", "-m", "first"])?;
    }
    fs::write(root.join(".env"), b"PRIVATE=alias-checkout\n")?;
    fs::write(neighbor.join(".env"), b"PRIVATE=alias-neighbor\n")?;
    let observed = inspect(&root)?;
    assert_ne!(
        observed["checkout"]["topology"]["root"]["identity"],
        inspect(&neighbor)?["checkout"]["topology"]["root"]["identity"]
    );
    let mut aliases = Vec::new();
    #[cfg(unix)]
    {
        let alias = temp.path().join("Symlink");
        std::os::unix::fs::symlink(&root, &alias)?;
        aliases.push(alias);
    }
    #[cfg(target_os = "macos")]
    aliases.push(temp.path().join("Checkout-cafe\u{301}"));
    #[cfg(windows)]
    {
        // Built-in /J creates a local directory junction. Fixed relative names
        // avoid passing paths through cmd's expansion/quoting syntax.
        let cmd = PathBuf::from(std::env::var_os("SystemRoot").ok_or("SystemRoot absent")?)
            .join("System32/cmd.exe");
        let result = Command::new(cmd)
            .current_dir(temp.path())
            .args(["/D", "/C", "mklink", "/J", "Junction", "Checkout"])
            .output()?;
        assert!(
            result.status.success(),
            "fixture directory junction creation failed"
        );
        aliases.push(temp.path().join("Junction"));
        aliases.push(temp.path().join("checkout"));
        aliases.push(root.canonicalize()?);
    }
    assert!(!aliases.is_empty(), "an actual platform alias is required");
    let identity = Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    };
    let at = format!("{:.3}", jiff::Timestamp::now());
    let mut store = Store::open(&state, true)?;
    let original = passports::plan(&mut store, &root, identity.clone(), &at)?;
    passports::apply(&mut store, &original, &original.digest()?, &identity, &at)?;
    for alias in &aliases {
        let alias_observation = inspect(alias)?;
        assert_eq!(
            alias_observation["checkout"]["topology"]["root"]["identity"],
            observed["checkout"]["topology"]["root"]["identity"]
        );
        assert_eq!(
            alias_observation["checkout"]["commit"],
            observed["checkout"]["commit"]
        );
        let plan = passports::plan(&mut store, alias, identity.clone(), &at)?;
        assert_eq!(plan.root_identity, original.root_identity);
        assert_eq!(plan.passport["stable_id"], original.passport["stable_id"]);
        passports::apply(&mut store, &plan, &plan.digest()?, &identity, &at)?;
        assert_eq!(&counts(&mut store)?[..2], &[1, 1]);
    }
    let pending = passports::plan(&mut store, &root, identity.clone(), &at)?;
    let before = counts(&mut store)?;
    let displaced = temp.path().join("Displaced");
    fs::rename(&root, &displaced)?;
    fs::create_dir(&root)?;
    fs::write(root.join(".env"), b"PRIVATE=replacement-root\n")?;
    assert!(passports::apply(&mut store, &pending, &pending.digest()?, &identity, &at).is_err());
    assert_eq!(counts(&mut store)?, before);
    assert!(!root.join(".ai-stp-v2-project").exists());
    assert!(!neighbor.join(".ai-stp-v2-project").exists());
    assert_eq!(fs::read(root.join(".env"))?, b"PRIVATE=replacement-root\n");
    assert_eq!(
        fs::read(displaced.join(".env"))?,
        b"PRIVATE=alias-checkout\n"
    );
    assert_eq!(
        fs::read(neighbor.join(".env"))?,
        b"PRIVATE=alias-neighbor\n"
    );
    #[cfg(unix)]
    fs::remove_file(temp.path().join("Symlink"))?;
    #[cfg(windows)]
    fs::remove_dir(temp.path().join("Junction"))?;
    println!(
        "checkout aliases: os={}, aliases={}, one passport, root replacement refused",
        std::env::consts::OS,
        aliases.len()
    );
    Ok(())
}
