//! Exact public GitHub source observation; authenticated publication is separate.

mod archive;
mod transport;

use serde_json::{Value, json};
use url::Url;

use crate::{
    canonical, digest,
    error::{Failure, Result},
    sources::{Source, snapshot},
    wire,
};

fn invalid() -> Failure {
    Failure::precondition("GitHub source identity does not match the requested public exact commit")
}

pub fn fetch(value: &str) -> Result<Value> {
    let Source::Github {
        repository,
        commit: Some(commit),
        subpath,
        ..
    } = super::parse(value, None)?
    else {
        return Err(Failure::input(
            "source fetch requires a GitHub address pinned to a full commit SHA",
        ));
    };
    if subpath
        .as_deref()
        .is_some_and(|path| !crate::artifacts::safe_path(path))
    {
        return Err(Failure::input(
            "the selected GitHub subpath is not portable",
        ));
    }
    let parsed = Url::parse(&repository).map_err(|_| invalid())?;
    let coordinate = parsed.path().trim_start_matches('/');
    let (owner, name) = coordinate.split_once('/').ok_or_else(invalid)?;
    let api = Url::parse(&format!("https://api.github.com/repos/{coordinate}/"))
        .map_err(|_| invalid())?;
    let client = transport::Client::new();
    let metadata = wire::parse(&client.get(
        Url::parse(&format!("https://api.github.com/repos/{coordinate}")).map_err(|_| invalid())?,
        2 * 1024 * 1024,
    )?)?;
    let repo_id = metadata["id"]
        .as_u64()
        .filter(|id| *id > 0 && *id <= 9_007_199_254_740_991)
        .ok_or_else(invalid)?;
    if metadata["private"] != false
        || !metadata["full_name"]
            .as_str()
            .is_some_and(|name| name.eq_ignore_ascii_case(coordinate))
    {
        return Err(invalid());
    }
    let revision = wire::parse(
        &client.get(
            api.join(&format!("commits/{commit}"))
                .map_err(|_| invalid())?,
            2 * 1024 * 1024,
        )?,
    )?;
    if revision["sha"] != commit {
        return Err(invalid());
    }
    let bytes = client.get(
        api.join(&format!("zipball/{commit}"))
            .map_err(|_| invalid())?,
        archive::MAX_ARCHIVE as u64,
    )?;
    let encoded = snapshot::encode(archive::selected(&bytes, subpath.as_deref())?)?;
    let license = metadata["license"]["spdx_id"]
        .as_str()
        .filter(|value| !value.is_empty() && value.len() <= 64 && *value != "NOASSERTION");
    let result = json!({"schema_version":1,"snapshot":{
        "kind":"git","canonical_coordinate":format!("git:{repository}@{commit}:{}",subpath.as_deref().unwrap_or(".")),
        "exact_identity":commit,"archive_digest":digest::bytes("ai-stp:artifact:v1", &bytes)?,
        "component_digest":encoded.digest,"subpath":subpath.unwrap_or_else(||".".into()),
        "repository_url":repository,"github_owner":owner,"github_name":name,"github_repo_id":repo_id,
        "observed_license":license,"file_paths":encoded.paths,
        "author_verified":false,"component_verified":false,"target_write":false,
        "fetched_at":format!("{:.3}",jiff::Timestamp::now()),
    },"artifact":encoded.artifact,"provenance":"github_observed","network_accessed":true,"filesystem_accessed":false});
    canonical::bytes(&result)?;
    Ok(result)
}
