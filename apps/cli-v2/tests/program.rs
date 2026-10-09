use std::{error::Error, fs};

use ai_stp_cli_v2::{invoke, program};
use serde_json::json;

#[test]
fn prefix_observations_distinguish_absence_claims_and_unfinished_work() -> Result<(), Box<dyn Error>>
{
    let directory = tempfile::tempdir()?;
    let parent = directory.path().canonicalize()?;
    let prefix = parent.join("cafe\u{301} program");
    let read = || program::inspect(&prefix, "bin/tool");
    let absent = read()?;
    assert_eq!(absent["prefix_state"], "missing");
    assert!(!prefix.exists());
    fs::create_dir(&prefix)?;
    assert_eq!(read()?["observation"]["versions"], json!([]));
    fs::create_dir(prefix.join("bin"))?;
    for version in ["1.0.0", "2.0.0"] {
        fs::create_dir(prefix.join(version))?;
        fs::write(prefix.join(version).join("tool"), b"not an executable")?;
    }
    fs::copy(prefix.join("1.0.0/tool"), prefix.join("bin/tool"))?;
    fs::write(prefix.join("bin/.tool.version"), b"1.0.0\n")?;
    let present = read()?;
    assert_eq!(present["installation_verified"], false);
    assert_eq!(present["execution_authorized"], false);
    let observed = &present["observation"];
    assert_eq!(observed["recorded_version"], "1.0.0");
    assert_eq!(observed["recorded_version_present"], true);
    assert!(observed["link_version"].is_null());
    assert_eq!(observed["entry_point"]["kind"], "file");
    fs::write(prefix.join("bin/.tool.version"), b"9.0.0\n")?;
    assert_eq!(read()?["observation"]["recorded_version_present"], false);
    fs::create_dir(prefix.join(".incoming-3.0.0"))?;
    fs::create_dir(prefix.join(".replaced-2.0.0"))?;
    fs::write(prefix.join("bin/.tool.version.incoming"), b"2.")?;
    fs::write(prefix.join("bin/.tool.manifest.json.incoming"), b"{")?;
    assert_eq!(
        read()?["observation"]["unfinished"]
            .as_array()
            .map(Vec::len),
        Some(4)
    );
    fs::write(prefix.join("bin/.tool.version"), b"../outside")?;
    assert!(read().is_err());
    fs::write(prefix.join("bin/.tool.version"), vec![b'1'; 1025])?;
    assert!(read().is_err());
    fs::remove_file(prefix.join("bin/.tool.version"))?;
    assert!(read()?["observation"]["recorded_version"].is_null());
    fs::rename(prefix.join("bin/tool"), prefix.join("bin/tool.cmd"))?;
    fs::write(prefix.join("bin/.tool.version"), b"2.0.0\n")?;
    assert_eq!(
        program::inspect(&prefix, "bin/tool.cmd")?["observation"]["recorded_version"],
        "2.0.0"
    );
    for entry in [
        "../tool",
        "bin/../tool",
        "bin/a/tool",
        "bin/.tool",
        "bin/",
        "tool",
    ] {
        assert!(program::inspect(&prefix, entry).is_err(), "{entry}");
    }
    fs::create_dir(prefix.join("bin/tool"))?;
    assert!(read().is_err());
    fs::remove_dir(prefix.join("bin/tool"))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::{PermissionsExt, symlink};
        symlink("../1.0.0/tool", prefix.join("bin/tool"))?;
        let linked = read()?;
        assert_eq!(linked["observation"]["link_version"], "1.0.0");
        assert_eq!(linked["observation"]["marker_matches_link"], false);
        fs::remove_file(prefix.join("bin/tool"))?;
        symlink(prefix.join("1.0.0/tool"), prefix.join("bin/tool"))?;
        assert_eq!(read()?["observation"]["link_version"], "1.0.0");
        fs::remove_file(prefix.join("bin/tool"))?;
        symlink("../1.0.0/missing", prefix.join("bin/tool"))?;
        assert_eq!(read()?["observation"]["entry_point"]["state"], "dangling");
        fs::remove_file(prefix.join("bin/tool"))?;
        symlink("../../outside", prefix.join("bin/tool"))?;
        assert!(read().is_err());
        fs::remove_file(prefix.join("bin/tool"))?;
        symlink("tool", prefix.join("bin/tool"))?;
        assert!(read().is_err());
        fs::remove_file(prefix.join("bin/tool"))?;
        symlink("../missing/../1.0.0/tool", prefix.join("bin/tool"))?;
        assert!(read().is_err());
        fs::remove_file(prefix.join("bin/tool"))?;
        use std::{ffi::OsString, os::unix::ffi::OsStringExt};
        symlink(OsString::from_vec(vec![0xff]), prefix.join("bin/tool"))?;
        assert!(read().is_err());
        fs::remove_file(prefix.join("bin/tool"))?;
        symlink(&prefix, parent.join("alias"))?;
        assert!(program::inspect(&parent.join("alias"), "bin/tool").is_err());
        symlink("1.0.0", prefix.join("3.0.0"))?;
        assert!(read().is_err());
        fs::remove_file(prefix.join("3.0.0"))?;
        fs::set_permissions(&prefix, fs::Permissions::from_mode(0o000))?;
        let inaccessible = read();
        fs::set_permissions(&prefix, fs::Permissions::from_mode(0o700))?;
        assert!(inaccessible.is_err());
    }
    #[cfg(windows)]
    {
        let alias = parent.join("junction");
        let made = std::process::Command::new("cmd.exe")
            .args(["/d", "/c", "mklink", "/J"])
            .arg(&alias)
            .arg(&prefix)
            .output()?;
        assert!(made.status.success());
        assert!(program::inspect(&alias, "bin/tool.cmd").is_err());
        fs::rename(&alias, prefix.join("3.0.0"))?;
        assert!(read().is_err());
        fs::remove_dir(prefix.join("3.0.0"))?;
    }
    let report = invoke([
        "ai-stp-v2".into(),
        "program".into(),
        "inspect".into(),
        "--prefix".into(),
        prefix.clone().into_os_string(),
        "--entry-point".into(),
        "bin/tool.cmd".into(),
        "--json".into(),
    ])
    .envelope();
    assert_eq!(report["ok"], true, "{report}");
    let reported = std::path::Path::new(report["data"]["prefix"].as_str().ok_or("prefix absent")?);
    assert_eq!(reported.canonicalize()?, prefix.canonicalize()?);
    assert_eq!(reported.file_name(), prefix.file_name());
    assert_eq!(fs::read(prefix.join("bin/tool.cmd"))?, b"not an executable");
    fs::remove_file(prefix.join("bin/.tool.version"))?;
    fs::create_dir(prefix.join("bin/.tool.version"))?;
    assert!(read().is_err());
    assert!(program::inspect(&parent.join("missing/nested"), "bin/tool").is_err());
    let crowded = parent.join("crowded");
    fs::create_dir(&crowded)?;
    for index in 0..1025 {
        fs::write(crowded.join(format!("entry-{index}")), [])?;
    }
    assert!(program::inspect(&crowded, "bin/tool").is_err());
    Ok(())
}
