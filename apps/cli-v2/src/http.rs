//! Anonymous bounded HTTP. Credentials, redirects and ambient proxies are absent.

use crate::{
    config,
    error::{ErrorKind, Failure, Result},
    wire,
};
use serde_json::Value;
use std::{net::IpAddr, path::Path, time::Duration};
use url::Url;

pub const MAX_BODY: u64 = 8 * 1024 * 1024;
pub struct Endpoint {
    pub base: Url,
}

impl Endpoint {
    pub fn configured(path: Option<&Path>) -> Result<Self> {
        let report = config::show(path, &[])?;
        let fields = report["values"]
            .as_array()
            .ok_or_else(|| Failure::new(ErrorKind::Internal, "configuration report is invalid"))?;
        if fields
            .iter()
            .find(|v| v["path"] == "catalog.enabled")
            .is_some_and(|v| v["value"] == false)
        {
            return Err(Failure::precondition(
                "the catalog is disabled by explicit configuration",
            ));
        }
        let text = fields
            .iter()
            .find(|v| v["path"] == "catalog.url")
            .and_then(|v| v["value"].as_str())
            .ok_or_else(|| Failure::input("catalog URL is absent"))?;
        Self::new(text)
    }

    pub fn new(text: &str) -> Result<Self> {
        let text = text.trim();
        let invalid = || {
            Failure::input(
                "catalog URL must use HTTPS, or literal loopback HTTP, without credentials, query or fragment",
            )
        };
        if text
            .chars()
            .any(|c| c.is_whitespace() || c.is_control() || c == '\\')
        {
            return Err(invalid());
        }
        let base = Url::parse(text).map_err(|_| invalid())?;
        let authority = text
            .split_once("://")
            .map(|(_, rest)| rest.split('/').next().unwrap_or(""))
            .ok_or_else(invalid)?;
        if !matches!(base.scheme(), "http" | "https")
            || base.host_str().is_none()
            || !base.username().is_empty()
            || base.password().is_some()
            || authority.contains('@')
            || base.query().is_some()
            || base.fragment().is_some()
        {
            return Err(invalid());
        }
        if base.scheme() == "http" {
            let host = if let Some(bracketed) = authority.strip_prefix('[') {
                bracketed.split(']').next().unwrap_or("")
            } else {
                authority.split(':').next().unwrap_or("")
            };
            if !host.eq_ignore_ascii_case("localhost")
                && !host
                    .parse::<IpAddr>()
                    .is_ok_and(|address| address.is_loopback())
            {
                return Err(invalid());
            }
        }
        Ok(Self { base })
    }

    pub fn route(&self, segments: &[&str], query: &[(&str, &str)]) -> Result<Url> {
        let mut url = self.base.clone();
        url.path_segments_mut()
            .map_err(|_| Failure::input("catalog URL cannot contain paths"))?
            .pop_if_empty()
            .extend(["v1", "catalog"])
            .extend(segments);
        if !query.is_empty() {
            url.query_pairs_mut().extend_pairs(query.iter().copied());
        }
        Ok(url)
    }

    pub fn get(&self, url: &Url) -> Result<Value> {
        let agent: ureq::Agent = ureq::Agent::config_builder()
            .http_status_as_error(false)
            .max_redirects(0)
            .proxy(None)
            .timeout_global(Some(Duration::from_secs(30)))
            .timeout_connect(Some(Duration::from_secs(5)))
            .build()
            .into();
        let mut response = agent
            .get(url.as_str())
            .header("Accept", "application/json")
            .header("Accept-Encoding", "identity")
            .header("X-AI-STP-Schema-Version", "1")
            .header(
                "User-Agent",
                concat!("ai-stp-cli-v2/", env!("CARGO_PKG_VERSION")),
            )
            .call()
            .map_err(transport)?;
        match response.status().as_u16() {
            200 => {}
            404 => {
                return Err(Failure::new(
                    ErrorKind::NotFound,
                    "the catalog object is not available",
                ));
            }
            408 | 425 | 429 | 500 | 502 | 503 | 504 => return Err(unavailable()),
            _ => {
                return Err(Failure::precondition(
                    "the catalog refused the request; no cached response may replace this answer",
                ));
            }
        }
        if response
            .headers()
            .get("X-AI-STP-Schema-Version")
            .is_some_and(|header| header != "1")
        {
            return Err(Failure::precondition(
                "catalog response uses an unsupported schema version",
            ));
        }
        let bytes = response
            .body_mut()
            .with_config()
            .limit(MAX_BODY)
            .read_to_vec()
            .map_err(transport)?;
        wire::parse(&bytes)
    }
}

pub fn unavailable() -> Failure {
    Failure::new(
        ErrorKind::Unavailable,
        "the catalog is temporarily unavailable; retry the read or use an explicit cache",
    )
}

fn transport(error: ureq::Error) -> Failure {
    match error {
        ureq::Error::Io(_)
        | ureq::Error::Timeout(_)
        | ureq::Error::HostNotFound
        | ureq::Error::ConnectionFailed
        | ureq::Error::BodyStalled => unavailable(),
        _ => Failure::precondition("catalog transport, TLS or response bounds were rejected"),
    }
}
