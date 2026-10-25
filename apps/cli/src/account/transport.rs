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
    #[serde(rename = "AI_STP_CONFLICT")]
    Conflict,
    #[serde(rename = "AI_STP_NOT_FOUND")]
    NotFound,
    #[serde(rename = "AI_STP_VALIDATION_ERROR")]
    Invalid,
    #[serde(rename = "AI_STP_PRECONDITION_FAILED")]
    Precondition,
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
    pub fn providers(&self) -> Result<Reply<super::providers::Providers>> {
        let agent = self.agent.borrow();
        let response = agent
            .get(format!("{}/v1/auth/providers", self.origin))
            .header("Accept", "application/json")
            .header("Accept-Encoding", "identity")
            .header("X-AI-STP-Schema-Version", "1")
            .call()
            .map_err(|_| unavailable())?;
        drop(agent);
        self.read(response)
    }

    pub fn reports(
        &self,
        id: Option<&str>,
        cursor: Option<&str>,
        body: Option<&[u8]>,
        credential: &Secret,
    ) -> Result<Reply<serde_json::Value>> {
        use super::reports::{invalid, uncertain};
        if id.is_some_and(|id| !crate::passport::stable_id(id, "report"))
            || cursor.is_some_and(|cursor| !super::reports::contract::cursor(cursor))
            || id.is_some() && (cursor.is_some() || body.is_some())
            || body.is_some() && cursor.is_some()
            || body.is_some_and(|body| body.len() > 65536)
        {
            return Err(invalid());
        }
        let path = id.map_or_else(|| "requests".to_owned(), |id| format!("requests/{id}"));
        let mut url =
            url::Url::parse(&format!("{}/v1/{path}", self.origin)).map_err(|_| invalid())?;
        if id.is_none() && body.is_none() {
            url.query_pairs_mut().append_pair("page_size", "100");
            if let Some(cursor) = cursor {
                url.query_pairs_mut().append_pair("cursor", cursor);
            }
        }
        let authorization = Zeroizing::new(format!("Bearer {}", credential.0.as_str()));
        let agent = self.agent.borrow();
        let response = if let Some(body) = body {
            agent
                .post(url.as_str())
                .header("Accept", "application/json")
                .header("Content-Type", "application/json")
                .header("Accept-Encoding", "identity")
                .header("X-AI-STP-Schema-Version", "1")
                .header("Authorization", authorization.as_str())
                .send(body)
        } else {
            agent
                .get(url.as_str())
                .header("Accept", "application/json")
                .header("Accept-Encoding", "identity")
                .header("X-AI-STP-Schema-Version", "1")
                .header("Authorization", authorization.as_str())
                .call()
        }
        .map_err(|_| uncertain())?;
        drop(agent);
        match self.response(response, 262144)? {
            Reply::Resource(bytes) => crate::wire::parse(&bytes)
                .map(Reply::Resource)
                .map_err(|_| uncertain()),
            Reply::Refused(code) => Ok(Reply::Refused(code)),
        }
    }

    pub fn me(&self, credential: &Secret) -> Result<Reply<Account>> {
        let authorization = Zeroizing::new(format!("Bearer {}", credential.0.as_str()));
        let agent = self.agent.borrow();
        let response = agent
            .get(format!("{}/v1/auth/me", self.origin))
            .header("Accept", "application/json")
            .header("Accept-Encoding", "identity")
            .header("X-AI-STP-Schema-Version", "1")
            .header("Authorization", authorization.as_str())
            .call()
            .map_err(|_| unavailable())?;
        drop(agent);
        self.read(response)
    }

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
        let response = request.send(body).map_err(|_| unavailable())?;
        drop(agent);
        self.read(response)
    }

    fn read<T: DeserializeOwned>(
        &self,
        response: ureq::http::Response<ureq::Body>,
    ) -> Result<Reply<T>> {
        match self.response(response, 65536)? {
            Reply::Resource(bytes) => serde_json::from_slice(&bytes)
                .map(Reply::Resource)
                .map_err(|_| super::invalid()),
            Reply::Refused(code) => Ok(Reply::Refused(code)),
        }
    }

    pub fn grants(
        &self,
        route: &str,
        body: Option<&[u8]>,
        credential: &Secret,
    ) -> Result<Reply<serde_json::Value>> {
        let parts: Vec<_> = route.split('/').collect();
        let valid = match parts.as_slice() {
            [""] => body.is_none(),
            ["direct" | "invitations"] => body.is_some(),
            ["invitations", id, "accept" | "revoke"] => {
                body.is_some() && crate::passport::stable_id(id, "invite")
            }
            [id, "revoke"] => body.is_some() && crate::passport::stable_id(id, "grant"),
            _ => false,
        };
        if !valid || body.is_some_and(|bytes| bytes.len() > 65536) {
            return Err(super::grants::invalid());
        }
        let url = if route.is_empty() {
            format!("{}/v1/grants", self.origin)
        } else {
            format!("{}/v1/grants/{route}", self.origin)
        };
        let authorization = Zeroizing::new(format!("Bearer {}", credential.0.as_str()));
        let agent = self.agent.borrow();
        let response = if let Some(body) = body {
            agent
                .post(&url)
                .header("Accept", "application/json")
                .header("Content-Type", "application/json")
                .header("Accept-Encoding", "identity")
                .header("X-AI-STP-Schema-Version", "1")
                .header("Authorization", authorization.as_str())
                .send(body)
        } else {
            agent
                .get(&url)
                .header("Accept", "application/json")
                .header("Accept-Encoding", "identity")
                .header("X-AI-STP-Schema-Version", "1")
                .header("Authorization", authorization.as_str())
                .call()
        }
        .map_err(|_| super::grants::uncertain())?;
        drop(agent);
        let response = self
            .response(response, crate::http::MAX_BODY)
            .map_err(|failure| {
                if matches!(failure.kind, ErrorKind::Unavailable) {
                    super::grants::uncertain()
                } else {
                    failure
                }
            })?;
        match response {
            Reply::Resource(bytes) => crate::wire::parse(&bytes).map(Reply::Resource),
            Reply::Refused(code) => Ok(Reply::Refused(code)),
        }
    }

    pub fn visibility(
        &self,
        route: &str,
        body: Option<&[u8]>,
        credential: &Secret,
    ) -> Result<Reply<serde_json::Value>> {
        let parts: Vec<_> = route.split('/').collect();
        let valid = match parts.as_slice() {
            [""] => body.is_some(),
            [id] => body.is_none() && crate::passport::stable_id(id, "plan"),
            [id, "confirm"] => body.is_some() && crate::passport::stable_id(id, "plan"),
            _ => false,
        };
        if !valid || body.is_some_and(|bytes| bytes.len() > 65536) {
            return Err(super::visibility::invalid());
        }
        let url = if route.is_empty() {
            format!("{}/v1/access/visibility/plans", self.origin)
        } else {
            format!("{}/v1/access/visibility/plans/{route}", self.origin)
        };
        let authorization = Zeroizing::new(format!("Bearer {}", credential.0.as_str()));
        let agent = self.agent.borrow();
        let response = if let Some(body) = body {
            agent
                .post(&url)
                .header("Accept", "application/json")
                .header("Content-Type", "application/json")
                .header("Accept-Encoding", "identity")
                .header("X-AI-STP-Schema-Version", "1")
                .header("Authorization", authorization.as_str())
                .send(body)
        } else {
            agent
                .get(&url)
                .header("Accept", "application/json")
                .header("Accept-Encoding", "identity")
                .header("X-AI-STP-Schema-Version", "1")
                .header("Authorization", authorization.as_str())
                .call()
        }
        .map_err(|_| super::visibility::uncertain())?;
        drop(agent);
        let response = self
            .response(response, crate::http::MAX_BODY)
            .map_err(|failure| {
                if matches!(failure.kind, ErrorKind::Unavailable) {
                    super::visibility::uncertain()
                } else {
                    failure
                }
            })?;
        match response {
            Reply::Resource(bytes) => crate::wire::parse(&bytes)
                .map(Reply::Resource)
                .map_err(|_| super::visibility::uncertain()),
            Reply::Refused(code) => Ok(Reply::Refused(code)),
        }
    }

    pub fn github(
        &self,
        body: Option<&[u8]>,
        credential: &Secret,
    ) -> Result<Reply<serde_json::Value>> {
        use super::github::uncertain;
        if body.is_some_and(|value| value.len() > 65536) {
            return Err(Failure::input(
                "the selected-source request exceeds its byte limit",
            ));
        }
        let authorization = Zeroizing::new(format!("Bearer {}", credential.0.as_str()));
        let agent = self.agent.borrow();
        let response = if let Some(body) = body {
            agent
                .post(format!("{}/v1/connectors/github/sources", self.origin))
                .header("Accept", "application/json")
                .header("Content-Type", "application/json")
                .header("Accept-Encoding", "identity")
                .header("X-AI-STP-Schema-Version", "1")
                .header("Authorization", authorization.as_str())
                .send(body)
        } else {
            agent
                .get(format!("{}/v1/connectors/github", self.origin))
                .header("Accept", "application/json")
                .header("Accept-Encoding", "identity")
                .header("X-AI-STP-Schema-Version", "1")
                .header("Authorization", authorization.as_str())
                .call()
        }
        .map_err(|_| uncertain())?;
        drop(agent);
        match self
            .response(response, crate::http::MAX_BODY)
            .map_err(|failure| {
                if matches!(failure.kind, ErrorKind::Unavailable) {
                    uncertain()
                } else {
                    failure
                }
            })? {
            Reply::Resource(bytes) => crate::wire::parse(&bytes)
                .map(Reply::Resource)
                .map_err(|_| uncertain()),
            Reply::Refused(code) => Ok(Reply::Refused(code)),
        }
    }

    pub fn sync(
        &self,
        request: &crate::sync::network::Request<'_>,
        credential: &Secret,
    ) -> Result<Reply<serde_json::Value>> {
        use crate::sync::network::{Request, uncertain};
        let authorization = Zeroizing::new(format!("Bearer {}", credential.0.as_str()));
        let agent = self.agent.borrow();
        let response = match request {
            Request::Push(value) => {
                let bytes = Zeroizing::new(crate::canonical::bytes(value)?);
                if bytes.len() as u64 > http::MAX_BODY {
                    return Err(Failure::input(
                        "the private sync request exceeds its byte limit",
                    ));
                }
                agent
                    .post(format!("{}/v1/sync/push", self.origin))
                    .header("Accept", "application/json")
                    .header("Content-Type", "application/json")
                    .header("Accept-Encoding", "identity")
                    .header("X-AI-STP-Schema-Version", "1")
                    .header("Authorization", authorization.as_str())
                    .send(bytes.as_slice())
            }
            Request::Pull { cursor, page_size } => {
                let mut url = format!("{}/v1/sync/pull?page_size={page_size}", self.origin);
                if let Some(cursor) = cursor {
                    url.push_str("&cursor=");
                    url.push_str(cursor);
                }
                agent
                    .get(&url)
                    .header("Accept", "application/json")
                    .header("Accept-Encoding", "identity")
                    .header("X-AI-STP-Schema-Version", "1")
                    .header("Authorization", authorization.as_str())
                    .call()
            }
        }
        .map_err(|_| uncertain())?;
        drop(agent);
        match self.response(response, http::MAX_BODY).map_err(|failure| {
            if matches!(failure.kind, ErrorKind::Unavailable) {
                uncertain()
            } else {
                failure
            }
        })? {
            Reply::Resource(bytes) => crate::wire::parse(&bytes).map(Reply::Resource),
            Reply::Refused(code) => Ok(Reply::Refused(code)),
        }
    }

    pub fn publication(
        &self,
        request: &crate::publication::client::Request<'_>,
        credential: &Secret,
    ) -> Result<Reply<serde_json::Value>> {
        use crate::publication::client::{Request, uncertain};
        let url = request.url(&self.origin)?;
        let authorization = Zeroizing::new(format!("Bearer {}", credential.0.as_str()));
        let body = match request {
            Request::Create(create) => Some(Zeroizing::new(create.bytes()?)),
            Request::Confirm { body, .. } => Some(Zeroizing::new(crate::canonical::bytes(body)?)),
            _ => None,
        };
        let agent = self.agent.borrow();
        let response = match request {
            Request::Create(_) | Request::Confirm { .. } => agent
                .post(&url)
                .header("Accept", "application/json")
                .header("Content-Type", "application/json")
                .header("Accept-Encoding", "identity")
                .header("X-AI-STP-Schema-Version", "1")
                .header("Authorization", authorization.as_str())
                .send(body.as_deref().ok_or_else(uncertain)?.as_slice()),
            Request::Bind { payload, .. } => agent
                .put(&url)
                .header("Accept", "application/json")
                .header("Content-Type", "application/octet-stream")
                .header("Accept-Encoding", "identity")
                .header("X-AI-STP-Schema-Version", "1")
                .header("Authorization", authorization.as_str())
                .send(*payload),
            Request::Status(_) => agent
                .get(&url)
                .header("Accept", "application/json")
                .header("Accept-Encoding", "identity")
                .header("X-AI-STP-Schema-Version", "1")
                .header("Authorization", authorization.as_str())
                .call(),
        }
        .map_err(|_| uncertain())?;
        drop(agent);
        // A malformed reply cannot establish whether a write was committed.
        match self
            .response(response, http::MAX_BODY)
            .map_err(|_| uncertain())?
        {
            Reply::Resource(bytes) => crate::wire::parse(&bytes)
                .map(Reply::Resource)
                .map_err(|_| uncertain()),
            Reply::Refused(code) => Ok(Reply::Refused(code)),
        }
    }

    fn response(
        &self,
        mut response: ureq::http::Response<ureq::Body>,
        limit: u64,
    ) -> Result<Reply<Zeroizing<Vec<u8>>>> {
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
                .limit(limit + 1)
                .read_to_vec()
                .map_err(|_| unavailable())?,
        );
        if bytes.len() as u64 > limit {
            return Err(super::invalid());
        }
        match status {
            200 | 201 => Ok(Reply::Resource(bytes)),
            400 | 401 | 403 | 404 | 409 | 410 | 412 | 422 | 429 => {
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

pub(super) fn publication_refusal(code: Code) -> Failure {
    let (kind, reason) = match code {
        Code::Conflict => (ErrorKind::Conflict, "request_conflict"),
        Code::Invalid => (ErrorKind::Input, "request_rejected"),
        Code::SlowDown => (ErrorKind::Unavailable, "rate_limited"),
        Code::NotFound => (ErrorKind::NotFound, "publication_not_found"),
        Code::Revoked => (ErrorKind::Precondition, "device_revoked"),
        Code::Unauthorized | Code::Expired => (ErrorKind::Precondition, "account_required"),
        Code::Forbidden => (ErrorKind::Precondition, "permission_denied"),
        Code::Precondition => (ErrorKind::Precondition, "publication_precondition_changed"),
        _ => (ErrorKind::Precondition, "remote_refusal"),
    };
    Failure::new(kind, "the publication API refused the request")
        .with_details([("reason".into(), reason.into())])
}

pub(super) fn sync_refusal(code: Code) -> Failure {
    let (kind, reason) = match code {
        Code::Conflict => (ErrorKind::Conflict, "request_conflict"),
        Code::Invalid => (ErrorKind::Input, "request_rejected"),
        Code::SlowDown => (ErrorKind::Unavailable, "rate_limited"),
        Code::Revoked => (ErrorKind::Precondition, "device_revoked"),
        Code::Unauthorized | Code::Expired => (ErrorKind::Precondition, "account_required"),
        Code::Forbidden => (ErrorKind::Precondition, "permission_denied"),
        _ => (ErrorKind::Precondition, "remote_refusal"),
    };
    Failure::new(kind, "the private sync API refused the request")
        .with_details([("reason".into(), reason.into())])
}

#[derive(Deserialize)]
pub(super) struct Account {
    pub schema_version: u32,
    pub account_id: String,
    pub device_id: Option<String>,
    pub account_status: String,
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
