//! Read-only native consumer handoff. No arguments or environment are retained.

#[cfg(any(target_os = "macos", windows))]
mod process;
#[cfg(test)]
mod tests;
#[cfg(test)]
pub(crate) static CONSUMERS: std::sync::Mutex<()> = std::sync::Mutex::new(());

use super::target::Target;
use crate::{
    error::{Failure, Result},
    files::{self, physical::DirectoryIdentity},
    harnesses,
};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

fn unavailable() -> Failure {
    Failure::new(
        crate::error::ErrorKind::Unavailable,
        "the native consumer boundary cannot be established; activation remains pending",
    )
}
fn active() -> Failure {
    Failure::precondition(
        "configuration is staged; finish the original or current harness session before publication",
    )
}
fn number(value: &str) -> Result<u64> {
    value
        .parse::<u64>()
        .ok()
        .filter(|v| *v > 0 && v.to_string() == value)
        .ok_or_else(unavailable)
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Stamp {
    Linux { boot_id: String, ticks: String },
    Macos { seconds: String, microseconds: u32 },
    Windows { filetime: String },
}
impl Stamp {
    fn os(&self) -> &'static str {
        match self {
            Self::Linux { .. } => "linux",
            Self::Macos { .. } => "macos",
            Self::Windows { .. } => "windows",
        }
    }
    fn validate(&self) -> Result<()> {
        match self {
            Self::Linux { boot_id, ticks } => {
                if boot_id.len() != 36
                    || !boot_id.bytes().enumerate().all(|(i, b)| {
                        if [8, 13, 18, 23].contains(&i) {
                            b == b'-'
                        } else {
                            b.is_ascii_hexdigit() && !b.is_ascii_uppercase()
                        }
                    })
                {
                    return Err(unavailable());
                }
                number(ticks)?;
            }
            Self::Macos {
                seconds,
                microseconds,
            } => {
                number(seconds)?;
                if *microseconds >= 1_000_000 {
                    return Err(unavailable());
                }
            }
            Self::Windows { filetime } => {
                number(filetime)?;
            }
        }
        Ok(())
    }
    fn after(&self, other: &Self) -> Result<bool> {
        self.validate()?;
        other.validate()?;
        Ok(match (self, other) {
            (
                Self::Linux {
                    boot_id: a,
                    ticks: x,
                },
                Self::Linux {
                    boot_id: b,
                    ticks: y,
                },
            ) => a != b || number(x)? > number(y)?,
            (
                Self::Macos {
                    seconds: a,
                    microseconds: x,
                },
                Self::Macos {
                    seconds: b,
                    microseconds: y,
                },
            ) => (number(a)?, x) > (number(b)?, y),
            (Self::Windows { filetime: a }, Self::Windows { filetime: b }) => {
                number(a)? > number(b)?
            }
            _ => return Err(unavailable()),
        })
    }
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Session {
    pub pid: u32,
    pub harness_id: String,
    pub stamp: Stamp,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Root {
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    path: PathBuf,
    physical: DirectoryIdentity,
}
impl Root {
    fn capture(target: &Target) -> Result<Self> {
        Ok(Self {
            path: target.root().to_owned(),
            physical: DirectoryIdentity::capture(&target.directory().map_err(|_| unavailable())?)?,
        })
    }
    fn open(&self) -> Result<Target> {
        let target = Target::resolve(&self.path, ".ai-stp-native").map_err(|_| unavailable())?;
        if Self::capture(&target)?.physical != self.physical {
            return Err(unavailable());
        }
        Ok(target)
    }
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Handoff {
    format: String,
    harness_id: String,
    native_os: String,
    roots: Vec<Root>,
    sessions: Vec<Session>,
    published: Option<Stamp>,
    confirmed: Option<Session>,
}
impl Handoff {
    pub fn prepare(harness: &str, targets: &[&Target]) -> Result<Self> {
        harnesses::definition(harness)?;
        if harness == "undefined" || !(1..=3).contains(&targets.len()) {
            return Err(unavailable());
        }
        for (i, a) in targets.iter().enumerate() {
            for b in targets.iter().skip(i + 1) {
                crate::files::physical::require_disjoint(
                    &a.directory().map_err(|_| unavailable())?,
                    &b.directory().map_err(|_| unavailable())?,
                )?;
            }
        }
        let native_os = crate::platform::current()
            .and_then(|v| v.split_once('/'))
            .ok_or_else(unavailable)?
            .0
            .into();
        let handoff = Self {
            format: "ai-stp-native-handoff/1".into(),
            harness_id: harness.into(),
            native_os,
            roots: targets
                .iter()
                .map(|t| Root::capture(t))
                .collect::<Result<_>>()?,
            sessions: observe(targets)?,
            published: None,
            confirmed: None,
        };
        handoff.validate()?;
        Ok(handoff)
    }
    fn validate(&self) -> Result<()> {
        harnesses::definition(&self.harness_id)?;
        if self.format != "ai-stp-native-handoff/1"
            || self.harness_id == "undefined"
            || !(1..=3).contains(&self.roots.len())
            || !matches!(self.native_os.as_str(), "linux" | "macos" | "windows")
            || self.sessions.len() > 256
            || self
                .sessions
                .windows(2)
                .any(|pair| pair[0].pid >= pair[1].pid)
        {
            return Err(unavailable());
        }
        for root in &self.roots {
            root.physical.validate()?;
            if !root.path.is_absolute()
                || !matches!(
                    (self.native_os.as_str(), &root.physical),
                    ("linux" | "macos", DirectoryIdentity::Unix { .. })
                        | ("windows", DirectoryIdentity::Windows { .. })
                )
            {
                return Err(unavailable());
            }
        }
        for session in self.sessions.iter().chain(&self.confirmed) {
            session.stamp.validate()?;
            harnesses::definition(&session.harness_id)?;
            if session.pid <= 1
                || session.harness_id == "undefined"
                || session.stamp.os() != self.native_os
            {
                return Err(unavailable());
            }
        }
        if let Some(moment) = &self.published {
            moment.validate()?;
            if moment.os() != self.native_os {
                return Err(unavailable());
            }
        }
        if let Some(confirmed) = &self.confirmed
            && (confirmed.harness_id != self.harness_id
                || self.sessions.contains(confirmed)
                || !confirmed
                    .stamp
                    .after(self.published.as_ref().ok_or_else(unavailable)?)?)
        {
            return Err(unavailable());
        }
        Ok(())
    }
    pub fn value(&self) -> Result<serde_json::Value> {
        self.validate()?;
        serde_json::to_value(self).map_err(|_| unavailable())
    }
    pub fn parse(value: serde_json::Value) -> Result<Self> {
        let handoff: Self = serde_json::from_value(value.clone()).map_err(|_| unavailable())?;
        if handoff.value()? != value {
            return Err(unavailable());
        }
        Ok(handoff)
    }
    /// A private, non-serializable guard that performs fresh checks on every use.
    pub fn require_idle(&self) -> Result<Idle> {
        self.validate()?;
        let idle = Idle {
            roots: self.roots.clone(),
            original: self.sessions.clone(),
        };
        idle.revalidate()?;
        Ok(idle)
    }
    pub fn published(&mut self) -> Result<()> {
        self.validate()?;
        if self.published.is_some() {
            return Err(unavailable());
        }
        self.require_idle()?.revalidate()?;
        self.published = Some(moment()?);
        self.validate()
    }
    /// Confirmation must come from the new harness's actual process ancestry.
    pub fn confirm(&mut self) -> Result<Session> {
        self.validate()?;
        if let Some(session) = &self.confirmed {
            return Ok(session.clone());
        }
        let publication = self.published.as_ref().ok_or_else(unavailable)?;
        for session in &self.sessions {
            if live(session)? {
                return Err(active());
            }
        }
        let targets = self
            .roots
            .iter()
            .map(Root::open)
            .collect::<Result<Vec<_>>>()?;
        let refs = targets.iter().collect::<Vec<_>>();
        let current = observe(&refs)?;
        let mut pid = std::process::id();
        for _ in 0..128 {
            let Some((parent, stamp)) = parent(pid)? else {
                break;
            };
            if let Some(session) = current
                .iter()
                .find(|s| s.pid == pid && s.stamp == stamp && s.harness_id == self.harness_id)
                && !self.sessions.contains(session)
                && session.stamp.after(publication)?
            {
                for target in &targets {
                    if !observe(&[target])?.contains(session) {
                        return Err(unavailable());
                    }
                }
                self.confirmed = Some(session.clone());
                self.validate()?;
                return Ok(session.clone());
            }
            if parent <= 1 || parent == pid {
                break;
            }
            pid = parent;
        }
        Err(Failure::precondition(
            "confirm this operation from a new harness session started after verified configuration publication",
        ))
    }
}
pub struct Idle {
    roots: Vec<Root>,
    original: Vec<Session>,
}
impl Idle {
    pub fn revalidate(&self) -> Result<()> {
        for session in &self.original {
            if live(session)? {
                return Err(active());
            }
        }
        let roots = self
            .roots
            .iter()
            .map(Root::open)
            .collect::<Result<Vec<_>>>()?;
        if !observe(&roots.iter().collect::<Vec<_>>())?.is_empty() {
            return Err(active());
        }
        Ok(())
    }
}
fn observe(targets: &[&Target]) -> Result<Vec<Session>> {
    #[cfg(target_os = "linux")]
    {
        Ok(crate::provider::runtime::native_sessions(targets)?
            .into_iter()
            .map(|s| Session {
                pid: s.pid,
                harness_id: s.harness_id,
                stamp: Stamp::Linux {
                    boot_id: s.boot_id,
                    ticks: s.started.to_string(),
                },
            })
            .collect())
    }
    #[cfg(any(target_os = "macos", windows))]
    {
        process::observe(targets)
    }
    #[cfg(not(any(target_os = "linux", target_os = "macos", windows)))]
    {
        let _ = targets;
        Err(unavailable())
    }
}
fn parent(pid: u32) -> Result<Option<(u32, Stamp)>> {
    #[cfg(target_os = "linux")]
    {
        Ok(
            crate::provider::runtime::native_parent(pid)?.map(|(p, boot, ticks)| {
                (
                    p,
                    Stamp::Linux {
                        boot_id: boot,
                        ticks: ticks.to_string(),
                    },
                )
            }),
        )
    }
    #[cfg(any(target_os = "macos", windows))]
    {
        process::parent(pid)
    }
    #[cfg(not(any(target_os = "linux", target_os = "macos", windows)))]
    {
        let _ = pid;
        Err(unavailable())
    }
}
fn live(session: &Session) -> Result<bool> {
    Ok(parent(session.pid)?.is_some_and(|(_, stamp)| stamp == session.stamp))
}
fn moment() -> Result<Stamp> {
    #[cfg(target_os = "linux")]
    {
        let stamp = crate::provider::runtime::native_published()?;
        Ok(Stamp::Linux {
            boot_id: stamp.boot_id,
            ticks: stamp.ticks.to_string(),
        })
    }
    #[cfg(any(target_os = "macos", windows))]
    {
        process::moment()
    }
    #[cfg(not(any(target_os = "linux", target_os = "macos", windows)))]
    {
        Err(unavailable())
    }
}
