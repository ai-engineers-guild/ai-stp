//! Repository-only native build, packaging and resource qualification.
mod build;
mod desktop;
mod release;
mod sbom;
#[cfg(test)]
mod tests;
mod wheel;

use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    ffi::OsString,
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{Duration, Instant},
};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
type Files = BTreeMap<String, Vec<u8>>;

fn require(condition: bool, message: &str) -> Result<()> {
    if condition {
        Ok(())
    } else {
        Err(std::io::Error::other(message).into())
    }
}

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../.."))
}

fn hash(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
fn encoded(value: &Value) -> Result<Vec<u8>> {
    let mut bytes = serde_json::to_vec_pretty(value)?;
    bytes.push(b'\n');
    Ok(bytes)
}

fn text(command: &mut Command) -> Result<String> {
    let bytes = capture(command, Duration::from_secs(120), false)?;
    Ok(String::from_utf8(bytes)?.trim().to_owned())
}

fn capture(command: &mut Command, timeout: Duration, silent: bool) -> Result<Vec<u8>> {
    let mut child = command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;
    let pipe = child.stdout.take().ok_or("child stdout is unavailable")?;
    let reader = std::thread::spawn(move || {
        let mut bytes = Vec::new();
        pipe.take(16 * 1024 * 1024 + 1)
            .read_to_end(&mut bytes)
            .map(|_| bytes)
    });
    let errors = child.stderr.take().ok_or("child stderr is unavailable")?;
    let error_reader = std::thread::spawn(move || {
        let mut bytes = Vec::new();
        errors
            .take(64 * 1024 + 1)
            .read_to_end(&mut bytes)
            .map(|_| bytes)
    });
    let started = Instant::now();
    let status = loop {
        if let Some(status) = child.try_wait()? {
            break status;
        }
        if started.elapsed() > timeout {
            let _ = child.kill();
            let _ = child.wait();
            return Err("native tool child timed out".into());
        }
        std::thread::sleep(Duration::from_millis(20));
    };
    let bytes = reader.join().map_err(|_| "child output reader failed")??;
    let errors = error_reader
        .join()
        .map_err(|_| "child error reader failed")??;
    require(errors.len() <= 64 * 1024, "child stderr exceeds its bound")?;
    if !silent {
        std::io::stderr().write_all(&errors)?;
    }
    require(status.success(), "native tool child failed")?;
    require(
        !silent || errors.is_empty(),
        "native metadata wrote to stderr",
    )?;
    require(
        bytes.len() <= 16 * 1024 * 1024,
        "child output exceeds its bound",
    )?;
    Ok(bytes)
}

fn run(command: &mut Command) -> Result<()> {
    require(command.status()?.success(), "native tool command failed")
}

fn options(args: &[OsString], names: &[&str]) -> Result<BTreeMap<String, String>> {
    require(
        args.len() == names.len() * 2,
        "missing or extra native tool options",
    )?;
    let mut values = BTreeMap::new();
    for pair in args.as_chunks::<2>().0 {
        let key = pair[0].to_str().ok_or("option is not UTF-8")?;
        let value = pair[1].to_str().ok_or("option value is not UTF-8")?;
        require(
            names.contains(&key) && values.insert(key.into(), value.into()).is_none(),
            "unknown or repeated native tool option",
        )?;
    }
    Ok(values)
}

fn executable(path: &Path) -> Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o755))?;
    }
    #[cfg(not(unix))]
    let _ = path;
    Ok(())
}

fn write_new(path: &Path, bytes: &[u8]) -> Result<()> {
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)?;
    file.write_all(bytes)?;
    Ok(())
}

fn isolated(binary: &Path, arguments: &[&str]) -> Result<Value> {
    let home = tempfile::tempdir()?;
    let mut command = Command::new(binary.canonicalize()?);
    command
        .args(arguments)
        .arg("--json")
        .env_clear()
        .current_dir(home.path());
    for key in ["SYSTEMROOT", "WINDIR"] {
        if let Some(value) = std::env::var_os(key) {
            command.env(key, value);
        }
    }
    command.env("PATH", "");
    for key in [
        "HOME",
        "USERPROFILE",
        "XDG_DATA_HOME",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
    ] {
        command.env(key, home.path());
    }
    let envelope: Value =
        serde_json::from_slice(&capture(&mut command, Duration::from_secs(30), true)?)?;
    require(
        envelope["ok"] == true,
        "native resource returned a failed envelope",
    )?;
    require(
        fs::read_dir(home.path())?.next().is_none(),
        "native metadata created persistent state",
    )?;
    Ok(envelope["data"].clone())
}

fn main() {
    if let Err(error) = main_result() {
        eprintln!("native-tools: {error}");
        std::process::exit(1);
    }
}

fn main_result() -> Result<()> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    std::env::set_current_dir(root())?;
    let command = args.first().and_then(|s| s.to_str()).unwrap_or("");
    match command {
        "build" => build::invoke(&args[1..]),
        "version" => { println!("{}", release::version()?); Ok(()) }
        "package" => release::package(&args[1..]),
        "verify" => release::verify(&args[1..]),
        "wheel" => wheel::package(&args[1..]),
        "probe" => {
            let opts = options(&args[1..], &["--binary", "--version"])?;
            release::probe(Path::new(&opts["--binary"]), &opts["--version"])
        },
        "desktop-stub" if args.len() == 1 => desktop::stub(),
        "desktop-build" if args.len() == 1 => desktop::build(),
        "desktop-probe" if args.len() == 1 => desktop::probe(None),
        "desktop-package-probe" if args.len() == 1 => desktop::packaged(),
        _ => Err("expected build <command...>, version, package, verify, wheel, desktop-stub, desktop-build, desktop-probe or desktop-package-probe".into()),
    }
}
