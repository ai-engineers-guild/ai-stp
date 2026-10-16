//! Project shared contracts into the self-contained published source crate.
use crate::{Result, require, root};
use std::{
    collections::BTreeSet,
    fs,
    path::{Component, Path, PathBuf},
};

fn files(path: &Path) -> Result<Vec<PathBuf>> {
    let mut result = Vec::new();
    if !path.exists() {
        return Ok(result);
    }
    for entry in fs::read_dir(path)? {
        let entry = entry?;
        let kind = entry.file_type()?;
        require(
            !kind.is_symlink(),
            "generated resource tree cannot contain links",
        )?;
        if kind.is_dir() {
            result.extend(files(&entry.path())?);
        } else if kind.is_file() {
            result.push(entry.path());
        }
    }
    result.sort();
    Ok(result)
}

pub fn sync(check: bool) -> Result<()> {
    let repo = root();
    let cli = repo.join("apps/cli");
    let output = cli.join("resources");
    let mut sources = BTreeSet::from([PathBuf::from("LICENSE")]);
    for source in files(&cli.join("src"))? {
        if source.extension().is_none_or(|extension| extension != "rs") {
            continue;
        }
        let text = fs::read_to_string(source)?;
        for suffix in text.split("\"/resources/").skip(1) {
            let name = suffix
                .split_once('"')
                .ok_or("resource literal is incomplete")?
                .0;
            let path = PathBuf::from(name);
            require(
                !path.as_os_str().is_empty()
                    && path.components().all(|c| matches!(c, Component::Normal(_))),
                "resource must be a repository-relative path",
            )?;
            sources.insert(path);
        }
    }
    for relative in &sources {
        let expected = fs::read(repo.join(relative))?;
        let target = output.join(relative);
        if fs::read(&target).ok().as_ref() != Some(&expected) {
            require(
                !check,
                &format!(
                    "native resource drift: {}; run just cli-gen",
                    relative.display()
                ),
            )?;
            fs::create_dir_all(target.parent().ok_or("resource parent missing")?)?;
            fs::write(target, expected)?;
        }
    }
    for target in files(&output)? {
        if !sources.contains(target.strip_prefix(&output)?) {
            require(!check, "obsolete native resource; run just cli-gen")?;
            fs::remove_file(target)?;
        }
    }
    println!("Native crate resources: {} current files", sources.len());
    Ok(())
}
