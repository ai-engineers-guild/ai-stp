//! Durable consumer identities; process inspection belongs to the host runtime.

use serde::{Deserialize, Serialize};

use super::invalid;
use crate::{error::Result, harnesses};

#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Session {
    pub boot_id: String,
    pub pid: u32,
    pub started: u64,
    pub harness_id: String,
}

#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Handoff {
    pub sessions: Vec<Session>,
    pub published: Option<Moment>,
    pub confirmed: Option<Session>,
}

#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Moment {
    pub boot_id: String,
    pub ticks: u64,
}

fn boot(value: &str) -> bool {
    value.len() == 36
        && value.bytes().enumerate().all(|(index, byte)| {
            if [8, 13, 18, 23].contains(&index) {
                byte == b'-'
            } else {
                byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()
            }
        })
}

impl Handoff {
    pub fn validate(&self) -> Result<()> {
        if self.sessions.len() > 256
            || self
                .sessions
                .windows(2)
                .any(|pair| pair[0].pid >= pair[1].pid)
            || self
                .published
                .as_ref()
                .is_some_and(|value| !boot(&value.boot_id) || value.ticks == 0)
        {
            return Err(invalid());
        }
        for session in self.sessions.iter().chain(&self.confirmed) {
            if !boot(&session.boot_id)
                || session.pid <= 1
                || session.started == 0
                || session.harness_id == "undefined"
            {
                return Err(invalid());
            }
            harnesses::definition(&session.harness_id)?;
        }
        if let Some(confirmed) = &self.confirmed
            && (self.published.as_ref().is_none_or(|after| {
                confirmed.boot_id == after.boot_id && confirmed.started <= after.ticks
            }) || self.sessions.contains(confirmed))
        {
            return Err(invalid());
        }
        Ok(())
    }
}
