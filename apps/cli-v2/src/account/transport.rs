//! Bounded same-origin requests; no redirects, ambient proxy or automatic retries.

use serde::{Deserialize, de::DeserializeOwned};
use std::cell::RefCell;
use zeroize::Zeroizing;

use super::model::Secret;
use crate::{
    error::{ErrorKind, Failure, Result},
    http,
};

pub(super) fn origin(value: &str) -> Result<String> {
    let url = http::Endpoint::new(value)?.base;
    if url.path() != "/" {
        return Err(Failure::input(
            "the account API URL must be an origin without a path",
        ));
    }
    Ok(url.origin().ascii_serialization())
}

pub(super) struct Api {
    origin: String,
    agent: RefCell<ureq::Agent>,
}

pub(super) enum Reply<T> {
    Resource(T),
    Refused(Code),
}

#[derive(Deserialize, PartialEq)]
pub(super) enum Code {
    #[serde(rename = "AI_STP_AUTHORIZATION_PENDING")]
    Pending,
    #[serde(rename = "AI_STP_AUTHORIZATION_EXPIRED")]
    Expired,
    #[serde(rename = "AI_STP_AUTHORIZATION_DECLINED")]
    Declined,
    #[serde(rename = "AI_STP_RATE_LIMITED")]
    SlowDown,
    #[serde(rename = "AI_STP_AUTH_REQUIRED")]
    Unauthorized,
    #[serde(rename = "AI_STP_PERMISSION_DENIED")]
    Forbidden,
    #[serde(rename = "AI_STP_DEVICE_REVOKED")]
    Revoked,
    #[serde(other)]
    Other,
}

#[derive(Deserialize)]
struct ErrorBody {
    code: Code,
}
#[derive(Deserialize)]
struct ErrorEnvelope {
    schema_version: u32,
    ok: bool,
    error: ErrorBody,
}

impl Api {
    pub fn new(value: &str) -> Result<Self> {
        Ok(Self {
            origin: origin(value)?,
            agent: RefCell::new(http::anonymous_agent()),
        })
    }

    pub fn post<T: DeserializeOwned>(
        &self,
        route: &str,
        body: &[u8],
        credential: Option<&Secret>,
    ) -> Result<Reply<T>> {
        if !matches!(
            route,
            "device" | "device/token" | "device/refresh" | "logout"
        ) {
            return Err(super::invalid());
        }
        let agent = self.agent.borrow();
        let mut request = agent
            .post(format!("{}/v1/auth/{route}", self.origin))
            .header("Accept", "application/json")
            .header("Content-Type", "application/json")
            .header("Accept-Encoding", "identity")
            .header("X-AI-STP-Schema-Version", "1")
            .header(
                "User-Agent",
                concat!("ai-stp-cli-v2/", env!("CARGO_PKG_VERSION")),
            );
        let authorization =
            credential.map(|token| Zeroizing::new(format!("Bearer {}", token.0.as_str())));
        if let Some(value) = &authorization {
            request = request.header("Authorization", value.as_str());
        }
        let mut response = request.send(body).map_err(|_| unavailable())?;
        drop(agent);
        http::discard_closed_pool(&self.agent, response.version());
        let status = response.status().as_u16();
        if response
            .headers()
            .get("X-AI-STP-Schema-Version")
            .is_some_and(|v| v != "1")
        {
            return Err(super::invalid());
        }
        let bytes = Zeroizing::new(
            response
                .body_mut()
                .with_config()
                .limit(65537)
                .read_to_vec()
                .map_err(|_| unavailable())?,
        );
        if bytes.len() > 65536 {
            return Err(super::invalid());
        }
        match status {
            200 | 201 => serde_json::from_slice(&bytes)
                .map(Reply::Resource)
                .map_err(|_| super::invalid()),
            400 | 401 | 403 | 404 | 409 | 410 | 429 => {
                let error: ErrorEnvelope =
                    serde_json::from_slice(&bytes).map_err(|_| super::invalid())?;
                if error.schema_version != 1 || error.ok {
                    return Err(super::invalid());
                }
                Ok(Reply::Refused(error.error.code))
            }
            408 | 425 | 500 | 502 | 503 | 504 => Err(unavailable()),
            _ => Err(Failure::precondition(
                "the account endpoint refused the request or attempted a redirect",
            )),
        }
    }
}

fn unavailable() -> Failure {
    Failure::new(
        ErrorKind::Unavailable,
        "the account response was not received; inspect the retained operation before issuing another request",
    )
}

#[derive(Deserialize)]
pub(super) struct Grant {
    pub schema_version: u32,
    pub device_code: Secret,
    pub user_code: String,
    pub verification_uri: String,
    pub verification_uri_complete: String,
    pub expires_in: u64,
    pub interval: u64,
}

#[derive(Deserialize)]
pub(super) struct Tokens {
    pub schema_version: u32,
    pub account_id: String,
    pub device_id: String,
    pub access_token: Secret,
    pub refresh_token: Secret,
    pub token_type: String,
    pub expires_in: u64,
}

#[derive(Deserialize)]
pub(super) struct Logout {
    pub schema_version: u32,
    pub revoked: bool,
}
