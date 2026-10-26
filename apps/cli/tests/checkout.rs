use std::{
    error::Error,
    ffi::OsStr,
    fs,
    path::{Path, PathBuf},
    process::Command,
};

use ai_stp_cli::{invoke, projects::checkout};
use serde_json::Value;

fn executable() -> Result<PathBuf, Box<dyn Error>> {
    let name = if cfg!(windows) { "git.exe" } else { "git" };
    std::env::split_paths(&std::env::var_os("PATH").ok_or("PATH absent")?)
        .filter(|path| path.is_absolute())
        .map(|path| path.join(name))
        .find(|path| path.is_file())
        .ok_or_else(|| "real Git is required for checkout acceptance".into())
}

fn git(root: &Path, args: &[&OsStr]) -> Result<(), Box<dyn Error>> {
    let output = Command::new(executable()?)
        .current_dir(root)
        .env("GIT_CONFIG_NOSYSTEM", "1")
        .env(
            "GIT_CONFIG_GLOBAL",
            if cfg!(windows) { "NUL" } else { "/dev/null" },
        )
        .env_remove("GIT_DIR")
        .env_remove("GIT_WORK_TREE")
        .env_remove("GIT_INDEX_FILE")
        .args([
            "-c",
            "user.name=Checkout fixture",
            "-c",
            "user.email=checkout@example.invalid",
        ])
        .args(args)
        .output()?;
    assert!(output.status.success(), "fixture Git operation failed");
    Ok(())
}

fn command(root: &Path, args: &[&str]) -> Result<(), Box<dyn Error>> {
    git(root, &args.iter().map(OsStr::new).collect::<Vec<_>>())
}

fn inspect(root: &Path) -> Result<Value, Box<dyn Error>> {
    Ok(checkout::observe(root, Some(&executable()?))?)
}

#[test]
fn real_checkout_distinguishes_commit_progress_from_routing_and_root_changes()
-> Result<(), Box<dyn Error>> {
    let temp = tempfile::tempdir()?;
    let root = temp.path().join("checkout-cafe\u{301}");
    fs::create_dir(&root)?;
    command(&root, &["init", "--initial-branch=main"])?;
    command(
        &root,
        &[
            "config",
            "remote.origin.url",
            "https://synthetic-private-token@example.invalid/first.git",
        ],
    )?;
    let unborn = inspect(&root)?;
    assert_eq!(unborn["checkout"]["head_state"], "unborn");
    assert_eq!(unborn["checkout"]["commit"], Value::Null);
    assert_eq!(unborn["checkout"]["remote_endpoint_count"], 1);
    assert_eq!(unborn, inspect(&root)?);
    command(&root, &["commit", "--allow-empty", "-m", "first"])?;
    let first = inspect(&root)?;
    assert_eq!(first["checkout"]["head_state"], "attached");
    assert_eq!(
        first["checkout"]["topology_digest"],
        unborn["checkout"]["topology_digest"]
    );
    command(&root, &["commit", "--allow-empty", "-m", "second"])?;
    let next = inspect(&root)?;
    assert_ne!(first["checkout"]["commit"], next["checkout"]["commit"]);
    assert_eq!(
        first["checkout"]["topology_digest"],
        next["checkout"]["topology_digest"]
    );
    assert_ne!(first["observation_digest"], next["observation_digest"]);
    command(
        &root,
        &[
            "config",
            "remote.origin.url",
            "https://synthetic-private-token@example.invalid/second.git",
        ],
    )?;
    let remapped = inspect(&root)?;
    assert_ne!(
        next["checkout"]["topology_digest"],
        remapped["checkout"]["topology_digest"]
    );
    command(&root, &["checkout", "--detach"])?;
    let detached = inspect(&root)?;
    assert_eq!(detached["checkout"]["head_state"], "detached");
    assert_ne!(
        detached["checkout"]["topology_digest"],
        remapped["checkout"]["topology_digest"]
    );
    assert_eq!(
        detached["checkout"]["commit"],
        remapped["checkout"]["commit"]
    );
    let child = root.join("child");
    fs::create_dir(&child)?;
    assert!(inspect(&child).is_err());
    command(&child, &["init", "--initial-branch=nested"])?;
    let nested = inspect(&child)?;
    assert_ne!(
        nested["checkout"]["topology_digest"],
        detached["checkout"]["topology_digest"]
    );
    let original_topology = detached["checkout"]["topology_digest"].clone();
    let serialized = serde_json::to_string(&[unborn, first, next, remapped, detached, nested])?;
    for secret in [
        "synthetic-private-token",
        "example.invalid",
        "first.git",
        "second.git",
    ] {
        assert!(!serialized.contains(secret));
    }
    assert!(!root.join(".ai-stp-v2-project").exists());
    assert!(!root.join(".git/index.lock").exists());
    let moved = temp.path().join("moved");
    fs::rename(&root, &moved)?;
    let old = inspect(&moved)?;
    assert_ne!(old["checkout"]["topology_digest"], original_topology);
    fs::create_dir(&root)?;
    command(&root, &["init", "--initial-branch=main"])?;
    assert_ne!(
        inspect(&root)?["checkout"]["topology_digest"],
        original_topology
    );
    assert_eq!(old["binding_created"], false);
    assert_eq!(old["installation_authority"], false);
    assert!(checkout::observe(&moved, Some(Path::new("relative-git"))).is_err());
    Ok(())
}

#[test]
fn real_sha256_checkout_and_bare_or_missing_repository_refusals() -> Result<(), Box<dyn Error>> {
    let temp = tempfile::tempdir()?;
    let root = temp.path().join("sha256");
    fs::create_dir(&root)?;
    assert!(inspect(&root).is_err());
    command(
        &root,
        &["init", "--object-format=sha256", "--initial-branch=main"],
    )?;
    command(&root, &["commit", "--allow-empty", "-m", "first"])?;
    let observed = inspect(&root)?;
    assert_eq!(observed["checkout"]["topology"]["object_format"], "sha256");
    assert_eq!(
        observed["checkout"]["commit"]
            .as_str()
            .ok_or("commit missing")?
            .len(),
        64
    );
    let bare = temp.path().join("bare");
    fs::create_dir(&bare)?;
    command(&bare, &["init", "--bare"])?;
    assert!(inspect(&bare).is_err());
    #[cfg(unix)]
    {
        let linked = temp.path().join("linked-marker");
        fs::create_dir(&linked)?;
        std::os::unix::fs::symlink(root.join(".git"), linked.join(".git"))?;
        assert!(inspect(&linked).is_err());
    }
    Ok(())
}

#[cfg(unix)]
#[test]
fn changing_remote_between_real_git_snapshots_refuses_without_exposing_values()
-> Result<(), Box<dyn Error>> {
    use std::os::unix::fs::PermissionsExt;
    fn quote(path: &Path) -> String {
        format!("'{}'", path.to_string_lossy().replace('\'', "'\\''"))
    }
    let temp = tempfile::tempdir()?;
    let root = temp.path().join("repository");
    fs::create_dir(&root)?;
    command(&root, &["init", "--initial-branch=main"])?;
    command(&root, &["commit", "--allow-empty", "-m", "first"])?;
    let wrapper = temp.path().join("git-observer");
    let counter = temp.path().join("count");
    let real = quote(&executable()?);
    let count = quote(&counter);
    let script = format!(
        "#!/bin/sh\nfor arg in \"$@\"; do\n if test \"$arg\" = --show-toplevel; then\n  n=0\n  if test -f {count}; then IFS= read -r n < {count}; fi\n  n=$((n + 1))\n  printf '%s\\n' \"$n\" > {count}\n  if test \"$n\" = 2; then {real} -C {} config remote.changed.url https://race-secret@example.invalid/repo || exit 81; fi\n fi\ndone\nexec {real} \"$@\"\n",
        quote(&root)
    );
    fs::write(&wrapper, script)?;
    fs::set_permissions(&wrapper, fs::Permissions::from_mode(0o755))?;
    let failure = checkout::observe(&root, Some(&wrapper))
        .err()
        .ok_or("changed routing was accepted")?;
    assert_eq!(fs::read_to_string(&counter)?, "2\n");
    assert!(!failure.message.contains("race-secret"));
    Ok(())
}

#[test]
fn real_worktree_and_repository_configuration_are_observed_without_external_includes()
-> Result<(), Box<dyn Error>> {
    let temp = tempfile::tempdir()?;
    let root = temp.path().join("repository");
    let worktree = temp.path().join("worktree");
    fs::create_dir(&root)?;
    command(&root, &["init", "--initial-branch=main"])?;
    command(&root, &["commit", "--allow-empty", "-m", "first"])?;
    git(
        &root,
        &[
            OsStr::new("worktree"),
            OsStr::new("add"),
            OsStr::new("-b"),
            OsStr::new("other"),
            worktree.as_os_str(),
        ],
    )?;
    let normal = inspect(&root)?;
    let linked = inspect(&worktree)?;
    assert_eq!(
        normal["checkout"]["topology"]["common_directory"],
        linked["checkout"]["topology"]["common_directory"]
    );
    assert_ne!(
        linked["checkout"]["topology"]["git_directory"],
        linked["checkout"]["topology"]["common_directory"]
    );
    assert_eq!(normal["checkout"]["commit"], linked["checkout"]["commit"]);
    command(&root, &["config", "extensions.worktreeConfig", "true"])?;
    command(
        &worktree,
        &[
            "config",
            "--worktree",
            "remote.special.url",
            "https://worktree-secret@example.invalid/repo",
        ],
    )?;
    let configured = inspect(&worktree)?;
    assert_ne!(
        configured["checkout"]["topology_digest"],
        linked["checkout"]["topology_digest"]
    );
    assert!(!serde_json::to_string(&configured)?.contains("worktree-secret"));
    let include = temp.path().join("outside.config");
    fs::write(
        &include,
        "[remote \"hidden\"]\nurl=https://hidden-secret@example.invalid/repo\n",
    )?;
    git(
        &root,
        &[
            OsStr::new("config"),
            OsStr::new("include.path"),
            include.as_os_str(),
        ],
    )?;
    let error = checkout::observe(&worktree, Some(&executable()?))
        .err()
        .ok_or("include was accepted")?;
    assert!(!error.message.contains("hidden-secret"));
    assert!(inspect(&root).is_err());
    Ok(())
}

#[test]
fn cli_ignores_ambient_git_routing_and_global_configuration() -> Result<(), Box<dyn Error>> {
    let temp = tempfile::tempdir()?;
    let root = temp.path().join("repository");
    let other = temp.path().join("other");
    fs::create_dir(&root)?;
    fs::create_dir(&other)?;
    command(&root, &["init", "--initial-branch=main"])?;
    command(&other, &["init", "--initial-branch=foreign"])?;
    let before = inspect(&root)?;
    let config = temp.path().join("global.config");
    fs::write(
        &config,
        "[include]\npath=does-not-exist\n[remote \"injected\"]\nurl=https://global-secret@example.invalid/repo\n",
    )?;
    let output = Command::new(env!("CARGO_BIN_EXE_ai-stp"))
        .args(["project", "checkout", "inspect", "--json", "--root"])
        .arg(&root)
        .arg("--git-executable")
        .arg(executable()?)
        .env("GIT_DIR", other.join(".git"))
        .env("GIT_WORK_TREE", &other)
        .env("GIT_CONFIG_GLOBAL", &config)
        .env("GIT_CONFIG_COUNT", "1")
        .env("GIT_CONFIG_KEY_0", "remote.injected.url")
        .env(
            "GIT_CONFIG_VALUE_0",
            "https://environment-secret@example.invalid/repo",
        )
        .output()?;
    assert!(output.status.success());
    let envelope: Value = serde_json::from_slice(&output.stdout)?;
    assert_eq!(envelope["data"], before);
    assert!(output.stderr.is_empty());
    assert!(!String::from_utf8(output.stdout)?.contains("secret"));
    let descriptor = invoke(["ai-stp", "help", "--agent", "--json"].map(Into::into)).envelope();
    assert!(serde_json::to_string(&descriptor)?.contains("git-executable"));
    Ok(())
}

#[cfg(unix)]
#[test]
fn link_preview_requires_an_owned_registered_attached_checkout_before_remote_access()
-> Result<(), Box<dyn Error>> {
    use ai_stp_cli::{account::project_links, identity, projects::passports, store::Store};
    let temp = tempfile::tempdir()?;
    let state = temp.path().join("state");
    let root = temp.path().join("repository");
    fs::create_dir(&state)?;
    fs::create_dir(&root)?;
    let at = format!("{:.3}", jiff::Timestamp::now());
    let initialization = identity::plan(&state, identity::Storage::File, &at)?;
    let native = identity::apply(&initialization, &initialization.digest()?, &at)?;
    let remote = "remote_project_01ARZ3NDEKTSV4RRFFQ69G5FAV";
    let git_executable = executable()?;
    let attempt = |path: &Path| {
        project_links::preview(&state, None, path, remote, None, Some(&git_executable))
    };
    assert!(attempt(&root).is_err());
    assert!(!root.join(".ai-stp-v2-project").exists());
    command(&root, &["init", "--initial-branch=main"])?;
    let mut store = Store::open(&state, true)?;
    let plan = passports::plan(&mut store, &root, native.context(), &at)?;
    passports::apply(&mut store, &plan, &plan.digest()?, &native.context(), &at)?;
    drop(store);
    let count = || -> Result<i64, Box<dyn Error>> {
        let mut store = Store::open(&state, false)?;
        Ok(store.transaction(|t| {
            t.query_row("SELECT count(*) FROM operation", [], |r| r.get(0))
                .map_err(|_| ai_stp_cli::error::Failure::precondition("fixture registry count"))
        })?)
    };
    let before = count()?;
    assert!(
        attempt(&root)
            .err()
            .ok_or("unborn checkout accepted")?
            .message
            .contains("attached committed")
    );
    command(&root, &["commit", "--allow-empty", "-m", "first"])?;
    let refusal = attempt(&root)
        .err()
        .ok_or("missing corporate context accepted")?;
    assert!(refusal.message.contains("context"));
    command(&root, &["checkout", "--detach"])?;
    assert!(
        attempt(&root)
            .err()
            .ok_or("detached checkout accepted")?
            .message
            .contains("attached committed")
    );
    let moved = temp.path().join("moved");
    fs::rename(&root, &moved)?;
    assert!(attempt(&moved).is_err());
    assert_eq!(count()?, before);
    assert!(!state.join("ai-stp-v2-account").exists());
    assert!(!state.join("ai-stp-v2-connections").exists());
    Ok(())
}
