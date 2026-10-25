//! Resolve installed libclang without downloading or modifying system tools.
#[cfg(target_os = "linux")]
use crate::hash;
use crate::{Result, root, run};
#[cfg(unix)]
use crate::{require, text};
use serde_json::Value;
#[cfg(target_os = "linux")]
use std::fs;
#[cfg(unix)]
use std::path::Path;
use std::{
    ffi::OsString,
    io::{BufRead, BufReader},
    path::PathBuf,
    process::{Command, Stdio},
};

#[cfg(unix)]
fn prepend(command: &mut Command, key: &str, paths: &[&Path]) -> Result<()> {
    let mut entries = paths.iter().map(|p| p.to_path_buf()).collect::<Vec<_>>();
    if let Some(value) = std::env::var_os(key) {
        entries.extend(std::env::split_paths(&value));
    }
    command.env(key, std::env::join_paths(entries)?);
    Ok(())
}

#[cfg(unix)]
fn flags(command: &mut Command, values: &[&str]) {
    let mut value = values
        .iter()
        .map(|s| format!("'{}'", s.replace('\'', "'\\''")))
        .collect::<Vec<_>>()
        .join(" ");
    if let Ok(existing) = std::env::var("BINDGEN_EXTRA_CLANG_ARGS") {
        value.push(' ');
        value.push_str(&existing);
    }
    command.env("BINDGEN_EXTRA_CLANG_ARGS", value);
}

pub fn invoke(arguments: &[OsString]) -> Result<()> {
    let program = arguments.first().ok_or("build requires a command")?;
    let mut command = Command::new(program);
    command
        .args(&arguments[1..])
        .current_dir(root().join("apps/cli"));
    configure(&mut command)?;
    run(&mut command)
}

/// Obtain the executable from Cargo itself, including redirected and nested caches.
pub fn cli_binary() -> Result<PathBuf> {
    let mut command = Command::new("cargo");
    command.current_dir(root().join("apps/cli")).args([
        "build",
        "--locked",
        "--release",
        "--bins",
        "--examples",
        "--message-format=json-render-diagnostics",
    ]);
    configure(&mut command)?;
    let mut child = command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .spawn()?;
    let stdout = child.stdout.take().ok_or("Cargo stdout is unavailable")?;
    let result = (|| -> Result<Option<PathBuf>> {
        let mut binary = None;
        for line in BufReader::new(stdout).lines() {
            let message: Value = serde_json::from_str(&line?)?;
            if message["reason"] == "compiler-artifact"
                && message["target"]["name"] == "ai-stp"
                && message["target"]["kind"] == serde_json::json!(["bin"])
                && let Some(path) = message["executable"].as_str()
            {
                if binary.is_some() {
                    return Err("Cargo reported multiple native CLI executables".into());
                }
                binary = Some(PathBuf::from(path));
            }
        }
        Ok(binary)
    })();
    if result.is_err() {
        let _ = child.kill();
    }
    let status = child.wait()?;
    let binary = result?;
    if !status.success() {
        return Err("native CLI build failed".into());
    }
    let binary = binary.ok_or("Cargo reported no native CLI executable")?;
    if !binary.is_absolute() || !binary.is_file() {
        return Err("Cargo reported an unavailable native CLI executable".into());
    }
    Ok(binary)
}

#[cfg(target_os = "linux")]
fn configure(command: &mut Command) -> Result<()> {
    let mut directories = if let Some(value) = std::env::var_os("LIBCLANG_PATH") {
        vec![value.into()]
    } else {
        let mut entries = fs::read_dir("/usr/lib")?
            .collect::<std::io::Result<Vec<_>>>()?
            .into_iter()
            .filter(|entry| entry.file_name().to_string_lossy().starts_with("llvm-"))
            .map(|entry| entry.path().join("lib"))
            .collect::<Vec<_>>();
        entries.sort();
        entries.reverse();
        entries
    };
    let mut libraries = Vec::new();
    for directory in directories.drain(..) {
        if directory.is_file() {
            libraries.push(directory);
            continue;
        }
        if !directory.is_dir() {
            continue;
        }
        let mut entries = fs::read_dir(directory)?
            .collect::<std::io::Result<Vec<_>>>()?
            .into_iter()
            .filter(|entry| {
                let name = entry.file_name();
                let name = name.to_string_lossy();
                name.starts_with("libclang.so")
                    || (name.starts_with("libclang-")
                        && !name.starts_with("libclang-cpp")
                        && name.contains(".so"))
            })
            .map(|entry| entry.path())
            .collect::<Vec<_>>();
        entries.sort();
        libraries.extend(entries);
    }
    let library = libraries
        .iter()
        .find(|p| p.is_file())
        .ok_or("install libclang development files or set LIBCLANG_PATH")?
        .canonicalize()?;
    let include = text(Command::new("cc").arg("-print-file-name=include"))?;
    require(
        Path::new(&include).is_absolute() && Path::new(&include).join("stdarg.h").is_file(),
        "C compiler standard headers are unavailable",
    )?;
    let metadata: Value = serde_json::from_str(&text(
        Command::new("cargo")
            .current_dir(root().join("apps/cli"))
            .args(["metadata", "--locked", "--no-deps", "--format-version", "1"]),
    )?)?;
    let target = PathBuf::from(
        metadata["target_directory"]
            .as_str()
            .ok_or("Cargo target directory is unavailable")?,
    );
    require(
        target.is_absolute(),
        "Cargo target directory must be absolute",
    )?;
    let directory = target
        .join("native-toolchain")
        .join(hash(&fs::read(&library)?));
    fs::create_dir_all(&directory)?;
    let link = directory.join("libclang.so");
    if let Ok(metadata) = fs::symlink_metadata(&link) {
        require(
            metadata.is_symlink(),
            "libclang cache entry must be a symbolic link",
        )?;
    }
    if link.canonicalize().ok().as_ref() != Some(&library) {
        let staged = tempfile::tempdir_in(&directory)?;
        std::os::unix::fs::symlink(&library, staged.path().join("libclang.so"))?;
        fs::rename(staged.path().join("libclang.so"), &link)?;
    }
    command.env("LIBCLANG_PATH", &directory);
    prepend(command, "LIBRARY_PATH", &[&directory])?;
    prepend(
        command,
        "LD_LIBRARY_PATH",
        &[&directory, library.parent().ok_or("library has no parent")?],
    )?;
    flags(command, &["-isystem", &include]);
    Ok(())
}

#[cfg(target_os = "macos")]
fn configure(command: &mut Command) -> Result<()> {
    let compiler = std::path::PathBuf::from(text(Command::new("xcrun").args(["--find", "clang"]))?);
    let directory = compiler
        .parent()
        .and_then(Path::parent)
        .ok_or("invalid Xcode compiler path")?
        .join("lib");
    require(
        directory.join("libclang.dylib").is_file(),
        "selected Xcode toolchain lacks libclang",
    )?;
    let sdk = text(Command::new("xcrun").arg("--show-sdk-path"))?;
    let resources = text(Command::new(&compiler).arg("-print-resource-dir"))?;
    command.env("LIBCLANG_PATH", &directory);
    prepend(command, "DYLD_FALLBACK_LIBRARY_PATH", &[&directory])?;
    flags(
        command,
        &[
            "-isysroot",
            &sdk,
            "-isystem",
            &format!("{resources}/include"),
        ],
    );
    Ok(())
}

#[cfg(windows)]
fn configure(_command: &mut Command) -> Result<()> {
    Ok(())
}
