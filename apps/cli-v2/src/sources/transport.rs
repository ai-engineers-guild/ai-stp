//! Anonymous public source reads with fixed authorities and one total deadline.

use std::{
    cell::RefCell,
    time::{Duration, Instant},
};

use url::Url;

use crate::{
    error::{ErrorKind, Failure, Result},
    http,
};

#[derive(Clone, Copy)]
pub(super) enum Service {
    Github,
    Go,
    Pypi,
    Npm,
    Crates,
    Pub,
}

pub(super) struct Client {
    service: Service,
    agent: RefCell<ureq::Agent>,
    started: Instant,
}

fn refused() -> Failure {
    Failure::precondition("public source transport or response bounds were refused")
}

fn transport(error: ureq::Error) -> Failure {
    if http::is_transient(&error) {
        Failure::new(
            ErrorKind::Unavailable,
            "public source transport is unavailable",
        )
    } else {
        refused()
    }
}

pub(super) fn allowed(service: Service, url: &Url) -> bool {
    let hosts: &[&str] = match service {
        Service::Github => &["api.github.com", "codeload.github.com", "github.com"],
        Service::Go => &["proxy.golang.org", "sum.golang.org"],
        Service::Pypi => &["pypi.org", "files.pythonhosted.org"],
        Service::Npm => &["registry.npmjs.org"],
        Service::Crates => &["crates.io", "static.crates.io"],
        Service::Pub => &["pub.dev", "storage.googleapis.com"],
    };
    url.scheme() == "https"
        && match (service, url.host_str()) {
            (Service::Pub, Some("storage.googleapis.com")) => {
                url.path().starts_with("/pub-packages/packages/") && url.query().is_none()
            }
            _ => true,
        }
        && url.host_str().is_some_and(|host| hosts.contains(&host))
        && url.port().is_none()
        && url.username().is_empty()
        && url.password().is_none()
        && url.fragment().is_none()
}

impl Client {
    pub(super) fn new(service: Service) -> Self {
        Self {
            service,
            agent: RefCell::new(http::anonymous_agent()),
            started: Instant::now(),
        }
    }

    pub(super) fn get(&self, mut url: Url, limit: u64) -> Result<Vec<u8>> {
        for hop in 0..=2 {
            if !allowed(self.service, &url) {
                return Err(refused());
            }
            let remaining = Duration::from_secs(30)
                .checked_sub(self.started.elapsed())
                .filter(|remaining| !remaining.is_zero())
                .ok_or_else(|| {
                    Failure::new(
                        ErrorKind::Unavailable,
                        "public source HTTP deadline expired",
                    )
                })?;
            let request = self
                .agent
                .borrow()
                .get(url.as_str())
                .header(
                    "Accept",
                    match self.service {
                        Service::Github => "application/vnd.github+json",
                        Service::Pub
                            if url.host_str() == Some("pub.dev")
                                && url.path().starts_with("/api/packages/") =>
                        {
                            "application/vnd.pub.v2+json"
                        }
                        Service::Go
                        | Service::Pypi
                        | Service::Npm
                        | Service::Crates
                        | Service::Pub => "*/*",
                    },
                )
                .header("Accept-Encoding", "identity")
                .header(
                    "User-Agent",
                    match self.service {
                        Service::Crates | Service::Pub => concat!(
                            "ai-stp-cli-v2/",
                            env!("CARGO_PKG_VERSION"),
                            " (+https://github.com/ai-engineers-guild/ai-stp)"
                        ),
                        _ => concat!("ai-stp-cli-v2/", env!("CARGO_PKG_VERSION")),
                    },
                );
            let request = match self.service {
                Service::Github => request.header("X-GitHub-Api-Version", "2026-03-10"),
                _ => request,
            };
            let mut response = request
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
                404 | 410 => {
                    return Err(Failure::new(
                        ErrorKind::NotFound,
                        "the public source is absent",
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
                        "the source service refused or rate-limited the anonymous source request",
                    )
                    .with_details([("retry_after_seconds".into(), seconds.into())]));
                }
                408 | 425 | 500 | 502 | 503 | 504 => {
                    return Err(Failure::new(
                        ErrorKind::Unavailable,
                        "public source service is temporarily unavailable",
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
