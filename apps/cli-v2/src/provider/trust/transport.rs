//! The fixed Sigstore authority, bounded anonymous reads and no redirect authority.

use std::{
    cell::RefCell,
    time::{Duration, Instant},
};

use super::{Repository, invalid};
use crate::{
    error::{ErrorKind, Failure, Result},
    http,
};

pub(super) struct Http {
    agent: RefCell<ureq::Agent>,
    started: Instant,
    requests: usize,
}

impl Http {
    pub(super) fn new() -> Self {
        Self {
            agent: RefCell::new(http::anonymous_agent()),
            started: Instant::now(),
            requests: 0,
        }
    }
}

impl Repository for Http {
    fn get(&mut self, name: &str, target: bool, limit: usize) -> Result<Option<Vec<u8>>> {
        let remaining = Duration::from_secs(60).saturating_sub(self.started.elapsed());
        if remaining.is_zero()
            || self.requests >= 64
            || name.len() > 256
            || name.starts_with('.')
            || name.is_empty()
            || !name.bytes().all(|b| {
                b.is_ascii_lowercase() || b.is_ascii_digit() || matches!(b, b'.' | b'_' | b'-')
            })
        {
            return Err(invalid());
        }
        self.requests += 1;
        let url = format!(
            "https://tuf-repo-cdn.sigstore.dev/{}{name}",
            if target { "targets/" } else { "" }
        );
        let mut response = self
            .agent
            .borrow()
            .get(&url)
            .header("Accept-Encoding", "identity")
            .header(
                "User-Agent",
                concat!("ai-stp-cli-v2/", env!("CARGO_PKG_VERSION")),
            )
            .config()
            .timeout_global(Some(remaining.min(Duration::from_secs(20))))
            .build()
            .call()
            .map_err(|_| {
                Failure::new(
                    ErrorKind::Unavailable,
                    "Sigstore trust metadata is unavailable",
                )
            })?;
        http::discard_closed_pool(&self.agent, response.version());
        match response.status().as_u16() {
            200 => (),
            403 | 404 if !target && name.ends_with(".root.json") => return Ok(None),
            _ => return Err(invalid()),
        }
        let bytes = response
            .body_mut()
            .with_config()
            .limit(limit as u64 + 1)
            .read_to_vec()
            .map_err(|_| invalid())?;
        if bytes.len() > limit {
            return Err(invalid());
        }
        Ok(Some(bytes))
    }
}
