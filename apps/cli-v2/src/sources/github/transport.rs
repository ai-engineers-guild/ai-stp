//! Anonymous GitHub reads with fixed HTTPS authorities and a single total deadline.

use std::{
    cell::RefCell,
    time::{Duration, Instant},
};

use url::Url;

use crate::{
    error::{ErrorKind, Failure, Result},
    http,
};

pub(super) struct Client {
    agent: RefCell<ureq::Agent>,
    started: Instant,
}

fn refused() -> Failure {
    Failure::precondition("GitHub source transport or response bounds were refused")
}

fn transport(error: ureq::Error) -> Failure {
    if http::is_transient(&error) {
        Failure::new(
            ErrorKind::Unavailable,
            "GitHub source transport is unavailable",
        )
    } else {
        refused()
    }
}

pub(super) fn allowed(url: &Url) -> bool {
    url.scheme() == "https"
        && matches!(
            url.host_str(),
            Some("api.github.com" | "codeload.github.com" | "github.com")
        )
        && url.port().is_none()
        && url.username().is_empty()
        && url.password().is_none()
        && url.fragment().is_none()
}

impl Client {
    pub(super) fn new() -> Self {
        Self {
            agent: RefCell::new(http::anonymous_agent()),
            started: Instant::now(),
        }
    }

    pub(super) fn get(&self, mut url: Url, limit: u64) -> Result<Vec<u8>> {
        for hop in 0..=2 {
            if !allowed(&url) {
                return Err(refused());
            }
            let remaining = Duration::from_secs(30)
                .checked_sub(self.started.elapsed())
                .filter(|remaining| !remaining.is_zero())
                .ok_or_else(|| {
                    Failure::new(
                        ErrorKind::Unavailable,
                        "GitHub source HTTP deadline expired",
                    )
                })?;
            let mut response = self
                .agent
                .borrow()
                .get(url.as_str())
                .header("Accept", "application/vnd.github+json")
                .header("Accept-Encoding", "identity")
                .header("X-GitHub-Api-Version", "2026-03-10")
                .header(
                    "User-Agent",
                    concat!("ai-stp-cli-v2/", env!("CARGO_PKG_VERSION")),
                )
                .config()
                .timeout_global(Some(remaining))
                .build()
                .call()
                .map_err(transport)?;
            http::discard_closed_pool(&self.agent, response.version());
            match response.status().as_u16() {
                200 => {}
                301 | 302 | 303 | 307 | 308 if hop < 2 => {
                    let location = response
                        .headers()
                        .get("Location")
                        .and_then(|value| value.to_str().ok())
                        .ok_or_else(refused)?;
                    url = url.join(location).map_err(|_| refused())?;
                    continue;
                }
                404 => {
                    return Err(Failure::new(
                        ErrorKind::NotFound,
                        "the public GitHub source is absent",
                    ));
                }
                403 | 429 => {
                    let seconds = response
                        .headers()
                        .get("Retry-After")
                        .and_then(|value| value.to_str().ok())
                        .and_then(|value| value.parse::<u64>().ok())
                        .or_else(|| {
                            response
                                .headers()
                                .get("X-RateLimit-Reset")
                                .and_then(|value| value.to_str().ok())
                                .and_then(|value| value.parse::<u64>().ok())
                                .map(|reset| {
                                    reset.saturating_sub(
                                        jiff::Timestamp::now().as_second().max(0) as u64
                                    )
                                })
                        })
                        .unwrap_or(60)
                        .clamp(1, 3600);
                    return Err(Failure::new(
                        ErrorKind::Unavailable,
                        "GitHub refused or rate-limited the anonymous source request",
                    )
                    .with_details([("retry_after_seconds".into(), seconds.into())]));
                }
                408 | 425 | 500 | 502 | 503 | 504 => {
                    return Err(Failure::new(
                        ErrorKind::Unavailable,
                        "GitHub source service is temporarily unavailable",
                    ));
                }
                _ => return Err(refused()),
            }
            let bytes = response
                .body_mut()
                .with_config()
                .limit(limit.checked_add(1).ok_or_else(refused)?)
                .read_to_vec()
                .map_err(transport)?;
            if bytes.len() as u64 > limit {
                return Err(refused());
            }
            return Ok(bytes);
        }
        Err(refused())
    }
}
