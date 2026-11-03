use super::{invalid, native};
use crate::installation::{forward, target::Target};
use crate::{
    authoring::contribution::{self, Format},
    digest,
    error::{ErrorKind, Result},
    files, passport,
    projection::Scope,
};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, path::PathBuf};

pub(super) type Identity = [u8; 25];
pub(super) const LIMIT: usize = 8 * 1024 * 1024;

#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Ownership {
    Whole,
    Contribution { parser_id: String, key: String },
}
impl Ownership {
    fn format(&self, path: &str) -> Result<Format> {
        let Self::Contribution { parser_id, key } = self else {
            return Err(invalid());
        };
        let format = Format::for_path(path)?;
        if key.is_empty()
            || key.len() > 255
            || key.chars().any(char::is_control)
            || parser_id
                != if format == Format::Toml {
                    "toml/1"
                } else {
                    "json/1"
                }
        {
            return Err(invalid());
        }
        Ok(format)
    }
}

#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Source {
    pub stable_id: String,
    pub version: String,
    pub passport_digest: String,
}
impl Source {
    pub(super) fn validate(&self) -> Result<()> {
        if !passport::stable_id(&self.stable_id, "component")
            || !passport::version_number(&self.version)
            || !hash(&self.passport_digest)
        {
            return Err(invalid());
        }
        Ok(())
    }
}

#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(super) struct Root {
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub path: PathBuf,
    pub identity: Identity,
}
impl Root {
    fn capture(target: &Target) -> Result<Self> {
        Ok(Self {
            path: target.root().to_owned(),
            identity: crate::installation::identity::directory(&native(target.directory())?)
                .map_err(|_| invalid())?,
        })
    }
    pub(super) fn open(&self) -> Result<Target> {
        let target = native(Target::resolve(&self.path, ".ai-stp-native"))?;
        if Self::capture(&target)? != *self {
            return Err(invalid());
        }
        Ok(target)
    }
}

/// Stable logical ownership is established by the native runtime, never by
/// trusting a serialized actor or the selected UI view.
#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Subject {
    pub(super) key: String,
    pub(super) harness: String,
    pub(super) scope: Scope,
    pub(super) root: Root,
}
impl Subject {
    pub fn capture(key: String, harness: String, scope: Scope, target: &Target) -> Result<Self> {
        let subject = Self {
            key,
            harness,
            scope,
            root: Root::capture(target)?,
        };
        subject.validate()?;
        Ok(subject)
    }
    pub(super) fn validate(&self) -> Result<()> {
        crate::harnesses::definition(&self.harness)?;
        if !hash(&self.key)
            || self.harness == "undefined"
            || !self.root.path.is_absolute()
            || !matches!(self.root.identity[0], 1 | 2)
        {
            return Err(invalid());
        }
        Ok(())
    }
}

#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(super) struct Value {
    pub digest: String,
    pub mode: Option<u32>,
}
impl Value {
    fn of(ownership: &Ownership, path: &str, bytes: &[u8], mode: u32) -> Result<Self> {
        Ok(match ownership {
            Ownership::Whole => Self {
                digest: digest::sha256(bytes),
                mode: Some(if cfg!(unix) { mode } else { 0o600 }),
            },
            Ownership::Contribution { key, .. } => Self {
                digest: digest::sha256(&contribution::extract(
                    ownership.format(path)?,
                    bytes,
                    key,
                )?),
                mode: None,
            },
        })
    }
    pub(super) fn validate(&self, kind: &Ownership) -> Result<()> {
        if !hash(&self.digest)
            || match (kind, self.mode) {
                (Ownership::Whole, Some(mode)) => mode & !0o777 != 0 || mode & 0o400 == 0,
                (Ownership::Contribution { .. }, None) => false,
                _ => true,
            }
        {
            return Err(invalid());
        }
        Ok(())
    }
}

#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(super) struct Address {
    pub parent: Identity,
    pub remaining: String,
    pub file: Option<Identity>,
}
impl Address {
    pub(super) fn same_file(&self, other: &Self) -> bool {
        (self.file.is_some() && self.file == other.file)
            || (self.parent == other.parent
                && unicase::UniCase::new(self.remaining.as_str())
                    == unicase::UniCase::new(other.remaining.as_str()))
    }
}

#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(super) struct Locator {
    pub root: Root,
    pub path: String,
    pub ownership: Ownership,
}
impl Locator {
    pub(super) fn observe(&self) -> Result<Observed> {
        let target = self.root.open()?;
        Observed::capture(&target, &self.path, self.ownership.clone())
    }
}

/// Actual held-object observations; previous configuration bytes are not retained.
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Observed {
    pub(super) locator: Locator,
    pub(super) address: Address,
    pub(super) before: forward::Observation,
    pub(super) value: Option<Value>,
}
impl Observed {
    pub fn capture(target: &Target, path: &str, ownership: Ownership) -> Result<Self> {
        if !crate::archive::safe_path(path) || path.split('/').count() > 32 {
            return Err(invalid());
        }
        let root = Root::capture(target)?;
        let (before, content) = native(forward::observe(target, path))?;
        let value = content
            .map(|content| Value::of(&ownership, path, &content.bytes, content.mode))
            .transpose();
        let value = match value {
            Ok(v) => v,
            Err(e) if matches!(e.kind, ErrorKind::NotFound) => None,
            Err(e) => return Err(e),
        };
        let (parent, remaining, file) = before.address(root.identity, path);
        Ok(Self {
            locator: Locator {
                root,
                path: path.into(),
                ownership,
            },
            address: Address {
                parent,
                remaining,
                file,
            },
            before,
            value,
        })
    }
    pub(super) fn unchanged(&self) -> Result<()> {
        let current = self.locator.observe()?;
        if current.before != self.before
            || current.address != self.address
            || current.value != self.value
        {
            return Err(invalid());
        }
        Ok(())
    }
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Desired {
    pub(super) observed: Observed,
    pub(super) value: Value,
    pub(super) source: Source,
}
impl Desired {
    pub fn capture(
        target: &Target,
        path: &str,
        ownership: Ownership,
        bytes: &[u8],
        mode: u32,
        source: Source,
    ) -> Result<Self> {
        source.validate()?;
        let observed = Observed::capture(target, path, ownership.clone())?;
        let value = Value::of(&ownership, path, bytes, mode)?;
        value.validate(&ownership)?;
        Ok(Self {
            observed,
            value,
            source,
        })
    }
}

pub struct Change {
    pub subject: Subject,
    pub desired: Vec<Desired>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Reference {
    pub subject: Subject,
    pub source: Source,
    pub locator: Locator,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Entry {
    pub id: String,
    pub address: Address,
    pub ownership: Ownership,
    pub value: Value,
    pub references: BTreeMap<String, Reference>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Snapshot {
    pub schema_version: u32,
    pub format: String,
    pub metadata_root: Identity,
    pub revision: String,
    pub entries: Vec<Entry>,
}
impl Snapshot {
    pub fn empty(root: Identity) -> Self {
        Self {
            schema_version: 1,
            format: "ai-stp-native-custody/1".into(),
            metadata_root: root,
            revision: "initial".into(),
            entries: Vec::new(),
        }
    }
    pub fn validate(&self, root: Identity) -> Result<()> {
        if self.schema_version != 1
            || self.format != "ai-stp-native-custody/1"
            || self.metadata_root != root
            || self.entries.len() > 20000
            || (self.revision != "initial" && !passport::stable_id(&self.revision, "operation"))
        {
            return Err(invalid());
        }
        let mut ids = std::collections::BTreeSet::new();
        for entry in &self.entries {
            if !passport::stable_id(&entry.id, "claim")
                || !ids.insert(&entry.id)
                || entry.references.is_empty()
                || entry.references.len() > 512
            {
                return Err(invalid());
            }
            entry.value.validate(&entry.ownership)?;
            for (key, reference) in &entry.references {
                reference.subject.validate()?;
                reference.source.validate()?;
                if key != &reference.subject.key
                    || reference.locator.root != reference.subject.root
                    || reference.locator.ownership != entry.ownership
                {
                    return Err(invalid());
                }
            }
        }
        if crate::canonical::bytes(&serde_json::to_value(self).map_err(|_| invalid())?)?.len()
            > LIMIT
        {
            return Err(invalid());
        }
        Ok(())
    }
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Effect {
    pub locator: Locator,
    pub before: Option<Value>,
    pub after: Option<Value>,
    pub observation: forward::Observation,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Review {
    pub(super) format: String,
    pub(super) operation_id: String,
    pub(super) before_digest: String,
    pub(super) after: Snapshot,
    pub(super) effects: Vec<Effect>,
    pub(super) native_plan: Option<serde_json::Value>,
}
impl Review {
    pub fn digest(&self) -> Result<String> {
        if let Some(plan) = &self.native_plan {
            let digest = digest::canonical("ai-stp:installation-operation:v1", plan)?;
            crate::installation::planning::Plan::parse(
                &serde_json::to_vec(plan).map_err(|_| invalid())?,
                &digest,
            )?;
            if plan["operation_id"] != self.operation_id {
                return Err(invalid());
            }
        }

        if self.after.revision != self.operation_id
            || self.format != "ai-stp-native-custody-review/1"
            || !passport::stable_id(&self.operation_id, "operation")
            || !hash(&self.before_digest)
            || self.effects.len() > 2000
        {
            return Err(invalid());
        }
        digest::canonical(
            "ai-stp:installation-operation:v1",
            &serde_json::to_value(self).map_err(|_| invalid())?,
        )
    }
    pub fn bind_native(mut self, plan: &crate::installation::planning::Plan) -> Result<Self> {
        self.native_plan = Some(plan.value()?);
        self.digest()?;
        Ok(self)
    }
    pub fn parse(bytes: &[u8], expected: &str) -> Result<Self> {
        if bytes.len() > LIMIT || !hash(expected) {
            return Err(invalid());
        }
        let value = crate::wire::parse(bytes)?;
        let review: Self = serde_json::from_value(value.clone()).map_err(|_| invalid())?;
        if review.digest()? != expected
            || serde_json::to_value(&review).map_err(|_| invalid())? != value
        {
            return Err(invalid());
        }
        review.after.validate(review.after.metadata_root)?;
        Ok(review)
    }
    pub fn value(&self) -> Result<serde_json::Value> {
        self.digest()?;
        serde_json::to_value(self).map_err(|_| invalid())
    }
}
pub(super) fn hash(value: &str) -> bool {
    crate::provider::plan::hash(value)
}
