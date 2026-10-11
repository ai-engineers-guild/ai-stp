//! Anonymous bounded HTTP. Credentials, redirects and ambient proxies are absent.

pub(crate) mod retry;

use crate::{
    config,
    error::{ErrorKind, Failure, Result},
    wire,
};
use serde_json::Value;
use std::{cell::RefCell, net::IpAddr, path::Path, time::Duration};
use url::Url;

pub const MAX_BODY: u64 = 8 * 1024 * 1024;
pub struct Endpoint {
    pub base: Url,
    agent: RefCell<ureq::Agent>,
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
        let agent = anonymous_agent();
        Ok(Self {
            base,
            agent: RefCell::new(agent),
        })
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
        wire::parse(&self.read(url, "application/json", MAX_BODY, Duration::from_secs(30))?)
    }

    pub(crate) fn read(
        &self,
        url: &Url,
        accept: &str,
        limit: u64,
        remaining: Duration,
    ) -> Result<Vec<u8>> {
        if remaining.is_zero() || url.origin() != self.base.origin() {
            return Err(Failure::precondition(
                "catalog request exceeds its origin or time boundary",
            ));
        }
        let mut response = self
            .agent
            .borrow()
            .get(url.as_str())
            .header("Accept", accept)
            .header("Accept-Encoding", "identity")
            .header("X-AI-STP-Schema-Version", "1")
            .header(
                "User-Agent",
                concat!("ai-stp-cli-v2/", env!("CARGO_PKG_VERSION")),
            )
            .config()
            .timeout_global(Some(remaining.min(Duration::from_secs(30))))
            .build()
            .call()
            .map_err(transport)?;
        discard_closed_pool(&self.agent, response.version());
        match response.status().as_u16() {
            200 => {}
            404 => {
                return Err(Failure::new(
                    ErrorKind::NotFound,
                    "the catalog object is not available",
                ));
            }
            408 | 425 | 429 | 500 | 502 | 503 | 504 => {
                return Err(retry::annotate(unavailable(), response.headers(), false));
            }
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
        // ureq's reader errors when its byte allowance reaches zero, even at EOF.
        // Permit one lookahead byte, then enforce our inclusive application bound.
        let bytes = response
            .body_mut()
            .with_config()
            .limit(
                limit
                    .checked_add(1)
                    .ok_or_else(|| Failure::input("catalog response bound overflow"))?,
            )
            .read_to_vec()
            .map_err(transport)?;
        if bytes.len() as u64 > limit {
            return Err(Failure::precondition(
                "catalog response exceeds its declared byte limit",
            ));
        }
        Ok(bytes)
    }
}

pub fn unavailable() -> Failure {
    Failure::new(
        ErrorKind::Unavailable,
        "the catalog is temporarily unavailable; retry the read or use an explicit cache",
    )
}

fn transport(error: ureq::Error) -> Failure {
    if is_transient(&error) {
        unavailable()
    } else {
        Failure::precondition("catalog transport, TLS or response bounds were rejected")
    }
}

pub(crate) fn is_transient(error: &ureq::Error) -> bool {
    matches!(
        error,
        ureq::Error::Io(_)
            | ureq::Error::Timeout(_)
            | ureq::Error::HostNotFound
            | ureq::Error::ConnectionFailed
            | ureq::Error::BodyStalled
    )
}

/// Anonymous transport defaults shared by catalog and public source acquisition.
pub(crate) fn anonymous_agent() -> ureq::Agent {
    ureq::Agent::config_builder()
        .http_status_as_error(false)
        .max_redirects(0)
        .proxy(None)
        .timeout_global(Some(Duration::from_secs(30)))
        .timeout_connect(Some(Duration::from_secs(5)))
        .build()
        .into()
}

pub(crate) fn discard_closed_pool(agent: &RefCell<ureq::Agent>, version: ureq::http::Version) {
    if version == ureq::http::Version::HTTP_10 {
        // ureq-proto 0.6.4 may pool HTTP/1.0 without keep-alive. Drop the pool
        // before consuming its body; HTTP/1.1 continues to reuse connections.
        let config = agent.borrow().config().clone();
        agent.replace(config.into());
    }
}
