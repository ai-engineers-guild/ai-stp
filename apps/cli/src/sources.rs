//! Bounded source intent parsing. An exact coordinate is not observed provenance.

pub mod github;
pub mod local;
pub mod package;
mod snapshot;
mod transport;

use std::path::{Path, PathBuf};

use percent_encoding::percent_decode_str;
use serde::Serialize;
use serde_json::{Value, json};
use url::Url;

use crate::{
    error::{Failure, Result},
    files,
};

#[derive(Clone, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Source {
    Published {
        owner: String,
        name: String,
        selector: Option<String>,
    },
    Github {
        repository: String,
        selector: Option<String>,
        commit: Option<String>,
        subpath: Option<String>,
    },
    Local {
        #[serde(serialize_with = "files::serialize_path")]
        path: PathBuf,
    },
    Collection {
        url: String,
    },
}

fn invalid() -> Failure {
    Failure::input("the source address is unsupported, ambiguous or unsafe")
}

fn segment(value: &str, limit: usize) -> bool {
    !value.is_empty()
        && value.len() <= limit
        && !matches!(value, "." | "..")
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-'))
        && value.as_bytes()[0].is_ascii_alphanumeric()
}

fn commit(value: &str) -> bool {
    value.len() == 40
        && value
            .bytes()
            .all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
}

fn selector(value: &str) -> Result<String> {
    if value.is_empty()
        || value.len() > 256
        || value.chars().any(|c| {
            c.is_whitespace() || c.is_control() || matches!(c, '\\' | '?' | '#' | '@' | ':')
        })
        || value
            .split('/')
            .any(|part| part.is_empty() || matches!(part, "." | ".."))
    {
        return Err(invalid());
    }
    Ok(value.into())
}

fn subpath(parts: &[String]) -> Result<Option<String>> {
    if parts.is_empty() {
        return Ok(None);
    }
    let path = parts.join("/");
    if path.len() > 512
        || parts.iter().any(|part| {
            part.is_empty()
                || matches!(part.as_str(), "." | "..")
                || part
                    .chars()
                    .any(|c| c.is_control() || matches!(c, '/' | '\\' | ':' | '\0'))
        })
    {
        return Err(invalid());
    }
    Ok(Some(path))
}

fn github(owner: &str, repo: &str, selected: Option<&str>, path: &[String]) -> Result<Source> {
    let repo = repo.strip_suffix(".git").unwrap_or(repo);
    if !segment(owner, 100) || !segment(repo, 100) {
        return Err(invalid());
    }
    let selected = selected.map(selector).transpose()?;
    let exact = selected.as_ref().filter(|value| commit(value)).cloned();
    Ok(Source::Github {
        repository: format!("https://github.com/{owner}/{repo}"),
        selector: selected,
        commit: exact,
        subpath: subpath(path)?,
    })
}

fn collection(owner: &str, handle: &str) -> Result<Source> {
    if !segment(owner, 100) || !segment(handle, 100) {
        return Err(invalid());
    }
    Ok(Source::Collection {
        url: format!("https://askill.sh/c/{owner}/{handle}"),
    })
}

fn url(source: &str) -> Result<Source> {
    // Inspect raw segments before WHATWG normalization can erase dot segments.
    let tail = source.strip_prefix("https://").ok_or_else(invalid)?;
    let (authority, raw_path) = tail.split_once('/').ok_or_else(invalid)?;
    if !["github.com", "askill.sh"].contains(&authority)
        || source.contains(['?', '#', '\\'])
        || source.chars().any(char::is_whitespace)
    {
        return Err(invalid());
    }
    let parsed = Url::parse(source).map_err(|_| invalid())?;
    if parsed.host_str() != Some(authority)
        || parsed.port().is_some()
        || !parsed.username().is_empty()
        || parsed.password().is_some()
    {
        return Err(invalid());
    }
    let raw_path = raw_path.strip_suffix('/').unwrap_or(raw_path);
    let mut parts = Vec::new();
    for part in raw_path.split('/') {
        let bytes = part.as_bytes();
        for (index, byte) in bytes.iter().enumerate() {
            if *byte == b'%'
                && !bytes
                    .get(index + 1..index + 3)
                    .is_some_and(|digits| digits.iter().all(u8::is_ascii_hexdigit))
            {
                return Err(invalid());
            }
        }
        let decoded = percent_decode_str(part)
            .decode_utf8()
            .map_err(|_| invalid())?;
        if decoded.is_empty()
            || matches!(decoded.as_ref(), "." | "..")
            || decoded
                .chars()
                .any(|c| c.is_control() || matches!(c, '/' | '\\' | '%'))
        {
            return Err(invalid());
        }
        parts.push(decoded.into_owned());
    }
    match (authority, parts.as_slice()) {
        ("github.com", [owner, repo]) => github(owner, repo, None, &[]),
        ("github.com", [owner, repo, form, selected, path @ ..])
            if form == "tree" || form == "blob" && !path.is_empty() =>
        {
            github(owner, repo, Some(selected), path)
        }
        ("askill.sh", [form, owner, handle]) if form == "c" => collection(owner, handle),
        _ => Err(invalid()),
    }
}

pub fn parse(value: &str, root: Option<&Path>) -> Result<Source> {
    if value.is_empty()
        || value.len() > 2048
        || value.trim() != value
        || value.chars().any(char::is_control)
    {
        return Err(invalid());
    }
    if value.contains("://") {
        return url(value);
    }
    if let Some(name) = value.strip_prefix('@') {
        let (owner, remainder) = name.split_once('/').ok_or_else(invalid)?;
        let (name, selected) = remainder
            .split_once('@')
            .map_or((remainder, None), |(name, selected)| (name, Some(selected)));
        if !segment(owner, 64) || !segment(name, 64) {
            return Err(invalid());
        }
        return Ok(Source::Published {
            owner: owner.into(),
            name: name.into(),
            selector: selected.map(selector).transpose()?,
        });
    }
    if let Some(name) = value.strip_prefix("col:") {
        let (owner, handle) = name.split_once('/').ok_or_else(invalid)?;
        return collection(owner, handle);
    }
    let windows_path = value.as_bytes().get(1) == Some(&b':') || value.starts_with(r"\\");
    let local = matches!(value, "." | ".." | "~")
        || ["./", "../", "/", "~/"]
            .iter()
            .any(|prefix| value.starts_with(prefix))
        || windows_path
        || cfg!(windows)
            && [".\\", "..\\"]
                .iter()
                .any(|prefix| value.starts_with(prefix));
    if local {
        if windows_path && (!cfg!(windows) || !Path::new(value).is_absolute()) {
            return Err(invalid());
        }
        let path = if value == "~" || value.starts_with("~/") {
            files::home()
                .filter(|path| path.is_absolute())
                .ok_or_else(invalid)?
                .join(value.strip_prefix("~/").unwrap_or(""))
        } else {
            PathBuf::from(value)
        };
        let path = if path.is_absolute() {
            path
        } else {
            root.filter(|path| path.is_absolute())
                .ok_or_else(|| {
                    Failure::input("a relative local source requires an explicit absolute root")
                })?
                .join(path)
        };
        if !path.is_absolute()
            || path
                .to_str()
                .is_none_or(|value| value.len() > 32768 || value.contains('\0'))
        {
            return Err(invalid());
        }
        // Keep '..' and exact Unicode bytes: resolving either would make a
        // filesystem claim and could change meaning across a symbolic link.
        return Ok(Source::Local { path });
    }
    let name = value.strip_prefix("gh:").unwrap_or(value);
    let (owner, remainder) = name.split_once('/').ok_or_else(invalid)?;
    if let Some((repo, selected)) = remainder.split_once('@') {
        return github(owner, repo, Some(selected), &[]);
    }
    let mut parts = remainder.split('/');
    let repo = parts.next().ok_or_else(invalid)?;
    github(
        owner,
        repo,
        None,
        &parts.map(str::to_owned).collect::<Vec<_>>(),
    )
}

pub fn inspect(value: &str, root: Option<&Path>, exact: Option<&str>) -> Result<Value> {
    let mut source = parse(value, root)?;
    if let Some(exact) = exact {
        if !commit(exact) {
            return Err(Failure::input(
                "an exact GitHub commit requires 40 lowercase hexadecimal characters",
            ));
        }
        let Source::Github { commit: held, .. } = &mut source else {
            return Err(invalid());
        };
        if held.as_ref().is_some_and(|held| held != exact) {
            return Err(Failure::precondition(
                "the supplied commit conflicts with the exact source address",
            ));
        }
        *held = Some(exact.into());
    }
    let source = serde_json::to_value(source).map_err(|_| invalid())?;
    Ok(
        json!({"schema_version":1,"source":source,"provenance":"not_observed",
        "network_accessed":false,"filesystem_accessed":false}),
    )
}
