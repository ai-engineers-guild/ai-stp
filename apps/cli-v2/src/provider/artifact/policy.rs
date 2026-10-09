//! Shared compiled publisher authority and unambiguous release sequences.

use super::{refused, wheel};
use crate::{
    error::{Failure, Result},
    harnesses,
    provenance::Publisher,
};
use toml_edit::DocumentMut;

pub(super) const POLICY: &str =
    include_str!("../../../../cli/src/ai_stp_cli/provider/provider-policy.toml");

pub(super) struct Request {
    pub project: String,
    pub filename: String,
    pub publisher: Publisher,
    pub sequence: u64,
    pub policy_id: String,
}

pub(super) fn request(harness: &str, version: &str, platform: &str) -> Result<Request> {
    harnesses::definition(harness)?;
    if version.len() > 32 {
        return Err(Failure::input(
            "the provider version exceeds its byte bound",
        ));
    }
    let numbers = version
        .split('.')
        .map(|part| {
            part.parse::<u32>()
                .ok()
                .filter(|number| number.to_string() == part)
                .ok_or_else(|| {
                    Failure::input("provider acquisition requires an exact canonical X.Y.Z version")
                })
        })
        .collect::<Result<Vec<_>>>()?;
    if numbers.len() != 3 {
        return Err(Failure::input(
            "provider acquisition requires an exact canonical X.Y.Z version",
        ));
    }
    if numbers[1] >= 1000 || numbers[2] >= 1000 {
        return Err(Failure::input(
            "provider policy sequences require minor and patch versions below 1000",
        ));
    }
    let sequence =
        u64::from(numbers[0]) * 1_000_000 + u64::from(numbers[1]) * 1000 + u64::from(numbers[2]);
    let tag = wheel::platform_tag(platform)?;
    let package = match harness {
        "claude-code" => "claude",
        "grok-build" => "grok",
        _ => harness,
    };
    let project = format!("{package}-setup-system");
    let policy: DocumentMut = POLICY.parse().map_err(|_| refused())?;
    if policy
        .get("schema_version")
        .and_then(toml_edit::Item::as_integer)
        != Some(2)
    {
        return Err(refused());
    }
    let minimum = policy
        .get("minimum_sequence")
        .and_then(toml_edit::Item::as_integer)
        .filter(|n| *n >= 0)
        .ok_or_else(refused)?;
    if sequence < minimum as u64
        || !policy
            .get("supported_protocols")
            .and_then(toml_edit::Item::as_array)
            .is_some_and(|values| values.iter().any(|value| value.as_integer() == Some(3)))
    {
        return Err(refused());
    }
    let rules = policy
        .get("index_publishers")
        .and_then(toml_edit::Item::as_array_of_tables)
        .ok_or_else(refused)?;
    let mut found = rules.iter().filter(|rule| {
        rule.get("pypi_project").and_then(toml_edit::Item::as_str) == Some(&project)
    });
    let rule = found.next().ok_or_else(refused)?;
    if found.next().is_some()
        || rule
            .get("verified_publisher")
            .and_then(toml_edit::Item::as_bool)
            != Some(true)
    {
        return Err(refused());
    }
    let field = |name| {
        rule.get(name)
            .and_then(toml_edit::Item::as_str)
            .filter(|s| !s.is_empty())
            .map(str::to_owned)
            .ok_or_else(refused)
    };
    let publisher = Publisher {
        repository: field("repository")?,
        workflow: field("workflow")?,
        environment: field("environment")?,
    };
    let repository = format!("github.com/{}", publisher.repository);
    if !policy
        .get("build_attestations")
        .and_then(toml_edit::Item::as_array_of_tables)
        .is_some_and(|rules| {
            rules.iter().any(|rule| {
                rule.get("repository").and_then(toml_edit::Item::as_str) == Some(&repository)
            })
        })
    {
        return Err(refused());
    }
    let filename = format!("{}-{version}-py3-none-{tag}.whl", project.replace('-', "_"));
    let id = policy
        .get("policy_id")
        .and_then(toml_edit::Item::as_str)
        .filter(|id| !id.is_empty())
        .ok_or_else(refused)?
        .to_owned();
    Ok(Request {
        project,
        filename,
        publisher,
        sequence,
        policy_id: id,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_sequences_cannot_alias_another_release() -> Result<()> {
        let last = request("claude-code", "1.999.999", "linux/x86_64")?;
        let next = request("claude-code", "2.0.0", "linux/x86_64")?;
        assert_eq!(last.sequence + 1, next.sequence);
        for version in [
            "1.1000.0", "1.0.1000", "01.0.0", "v1.0.0", "1.0.0rc1", "latest",
        ] {
            assert!(request("claude-code", version, "linux/x86_64").is_err());
        }
        assert!(request("unknown", "1.0.0", "linux/x86_64").is_err());
        assert!(request("claude-code", "1.0.0", "linux/unknown").is_err());
        Ok(())
    }
}
