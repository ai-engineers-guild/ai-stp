//! Durable physical file/contribution references shared by native contexts.
//!
//! This coordinator stores metadata and verifies actual file values. The native
//! runtime separately owns authorization, handoff and the configuration writer.

mod effects;
mod model;
mod placement;
#[cfg(test)]
mod tests;
use crate::{
    digest,
    error::{Failure, Result},
    installation::{
        forward::{self, Admission, Progress, Writer},
        target::Target,
    },
};
pub use model::{Change, Desired, Observed, Ownership, Review, Source, Subject};
use model::{Effect, Entry, Identity, Reference, Snapshot};
pub use placement::user_directory;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
};
const CONTROL: &str = ".ai-stp-custody-transactions";
const STATE: &str = "custody.json";
fn invalid() -> Failure {
    Failure::precondition(
        "the physical native custody, original operation or owned file value changed",
    )
}
fn native<T>(value: super::Result<T>) -> Result<T> {
    value.map_err(|error| {
        invalid().with_details([("reason".into(), error.reason().as_str().into())])
    })
}
fn encode(value: &impl serde::Serialize) -> Result<Vec<u8>> {
    let bytes = crate::canonical::bytes(&serde_json::to_value(value).map_err(|_| invalid())?)?;
    if bytes.len() > model::LIMIT {
        return Err(invalid());
    }
    Ok(bytes)
}
fn state_digest(value: &Snapshot) -> Result<String> {
    digest::canonical(
        "ai-stp:installation-operation:v1",
        &serde_json::to_value(value).map_err(|_| invalid())?,
    )
}

pub struct Custody {
    target: Target,
    writer: Writer,
    identity: Identity,
    _namespace: Option<crate::files::OwnedDirectory>,
}
impl Custody {
    /// Acquire the runtime-selected private metadata root. Configuration targets
    /// are never created or modified by this constructor.
    pub fn open(path: &Path) -> Result<Self> {
        let target = native(Target::resolve(path, CONTROL))?;
        let directory = native(target.directory())?;
        #[cfg(unix)]
        {
            use cap_std::fs::PermissionsExt;
            if directory
                .dir_metadata()
                .map_err(|_| invalid())?
                .permissions()
                .mode()
                & 0o777
                != 0o700
            {
                return Err(invalid());
            }
        }
        #[cfg(windows)]
        crate::files::document::windows::private(&directory, true).map_err(|_| invalid())?;
        let identity =
            crate::installation::identity::directory(&directory).map_err(|_| invalid())?;
        let writer = native(Writer::acquire(&target, CONTROL))?;
        Ok(Self {
            target,
            writer,
            identity,
            _namespace: None,
        })
    }
    /// Join the one OS-user coordinator, independently of state, HOME and XDG
    /// selectors. This explicitly initializes only private operational metadata.
    pub fn open_user() -> Result<Self> {
        let (path, namespace) = placement::initialize()?;
        let mut custody = Self::open(&path)?;
        custody._namespace = Some(namespace);
        Ok(custody)
    }

    fn private_root(&self) -> Result<()> {
        let directory = native(self.target.directory())?;
        #[cfg(unix)]
        {
            use cap_std::fs::PermissionsExt;
            if directory
                .dir_metadata()
                .map_err(|_| invalid())?
                .permissions()
                .mode()
                & 0o777
                != 0o700
            {
                return Err(invalid());
            }
        }
        #[cfg(windows)]
        crate::files::document::windows::private(&directory, true).map_err(|_| invalid())?;
        Ok(())
    }
    fn snapshot(&self) -> Result<Snapshot> {
        self.private_root()?;
        let (_, content) = native(self.writer.read(STATE))?;
        let snapshot = match content {
            Some(content) => {
                if content.bytes.len() > model::LIMIT {
                    return Err(invalid());
                }
                serde_json::from_value(crate::wire::parse(&content.bytes)?)
                    .map_err(|_| invalid())?
            }
            None => Snapshot::empty(self.identity),
        };
        snapshot.validate(self.identity)?;
        Ok(snapshot)
    }
    pub(crate) fn physical_identity(&self) -> Result<crate::files::physical::DirectoryIdentity> {
        self.private_root()?;
        crate::files::physical::DirectoryIdentity::capture(&native(self.target.directory())?)
    }
    pub fn inspect(&self) -> Result<Value> {
        let snapshot = self.snapshot()?;
        Ok(
            json!({"revision":snapshot.revision,"claims":snapshot.entries,"authorization_granted":false}),
        )
    }
    pub fn review(&self, operation_id: String, changes: &[Change]) -> Result<Review> {
        if !(1..=3).contains(&changes.len())
            || !crate::passport::stable_id(&operation_id, "operation")
        {
            return Err(invalid());
        }
        let before = self.snapshot()?;
        let mut after = before.clone();
        let mut subjects = BTreeSet::new();
        let mut observations = BTreeMap::new();
        for change in changes {
            change.subject.validate()?;
            if !subjects.insert(change.subject.key.clone()) || change.desired.len() > 2000 {
                return Err(invalid());
            }
            let target = change.subject.root.open()?;
            for entry in &before.entries {
                for reference in entry.references.values() {
                    if reference.subject.root.identity == change.subject.root.identity {
                        if reference.subject.scope != change.subject.scope
                            || (change.subject.scope == crate::projection::Scope::Global
                                && reference.subject.harness != change.subject.harness)
                        {
                            return Err(invalid());
                        }
                    } else {
                        let other = reference.subject.root.open()?;
                        crate::files::physical::require_disjoint(
                            &native(target.directory())?,
                            &native(other.directory())?,
                        )
                        .map_err(|_| invalid())?;
                    }
                }
            }
            for entry in &before.entries {
                if let Some(reference) = entry.references.get(&change.subject.key) {
                    let mut locator = reference.locator.clone();
                    locator.root = change.subject.root.clone();
                    let observed = locator.observe()?;
                    if observed.value.as_ref() != Some(&entry.value)
                        || (entry.address.file.is_some()
                            && entry.address.file != observed.address.file)
                    {
                        return Err(invalid());
                    }
                    observations.insert(entry.id.clone(), observed);
                }
            }
            for entry in &mut after.entries {
                entry.references.remove(&change.subject.key);
            }
        }
        let mut desired_files = Vec::new();
        for change in changes {
            for desired in &change.desired {
                desired.source.validate()?;
                desired.observed.unchanged()?;
                if desired.observed.locator.root != change.subject.root
                    || desired_files.iter().any(|address: &model::Address| {
                        address.same_file(&desired.observed.address)
                    })
                {
                    return Err(invalid());
                }
                desired_files.push(desired.observed.address.clone());
                let mut matched = None;
                for (index, entry) in after.entries.iter().enumerate() {
                    if entry.address.same_file(&desired.observed.address) {
                        match (&entry.ownership, &desired.observed.locator.ownership) {
                            (Ownership::Whole, Ownership::Whole) => matched = Some(index),
                            (
                                Ownership::Contribution {
                                    parser_id: a,
                                    key: ak,
                                },
                                Ownership::Contribution {
                                    parser_id: b,
                                    key: bk,
                                },
                            ) if a == b => {
                                if ak == bk {
                                    matched = Some(index);
                                }
                            }
                            _ => return Err(invalid()),
                        }
                    }
                }
                let index = if let Some(index) = matched {
                    let entry = &after.entries[index];
                    if desired.observed.value.as_ref() != Some(&entry.value)
                        || (entry.address.file.is_some()
                            && entry.address.file != desired.observed.address.file)
                        || (entry.value != desired.value && !entry.references.is_empty())
                    {
                        return Err(invalid());
                    }
                    index
                } else {
                    if desired.observed.value.is_some() {
                        return Err(invalid());
                    }
                    after.entries.push(Entry {
                        id: format!("claim_{}", ulid::Ulid::generate()),
                        address: desired.observed.address.clone(),
                        ownership: desired.observed.locator.ownership.clone(),
                        value: desired.value.clone(),
                        references: BTreeMap::new(),
                    });
                    after.entries.len() - 1
                };
                let entry = &mut after.entries[index];
                observations.insert(entry.id.clone(), desired.observed.clone());
                entry.value = desired.value.clone();
                entry.references.insert(
                    change.subject.key.clone(),
                    Reference {
                        subject: change.subject.clone(),
                        source: desired.source.clone(),
                        locator: desired.observed.locator.clone(),
                    },
                );
            }
        }
        let mut effects = Vec::new();
        for (id, observed) in observations {
            let new = after
                .entries
                .iter()
                .find(|entry| entry.id == id && !entry.references.is_empty())
                .map(|entry| entry.value.clone());
            effects.push(Effect {
                locator: observed.locator,
                before: observed.value,
                after: new,
                observation: observed.before,
            });
        }
        after.entries.retain(|entry| !entry.references.is_empty());
        after.revision = operation_id.clone();
        after.validate(self.identity)?;
        let review = Review {
            format: "ai-stp-native-custody-review/1".into(),
            operation_id,
            before_digest: state_digest(&before)?,
            after,
            effects,
            native_plan: None,
        };
        review.digest()?;
        Ok(review)
    }
    fn admission(review: &Review) -> Result<Admission> {
        Ok(Admission {
            operation_id: review.operation_id.clone(),
            plan_digest: review.digest()?,
            operation: "replace".into(),
            target_precondition_digest: review.before_digest.clone(),
            target_scope: None,
        })
    }
    pub fn prepare(&mut self, review: &Review, expected: &str) -> Result<Value> {
        if review.digest()? != expected {
            return Err(invalid());
        }
        self.private_root()?;
        let admission = Self::admission(review)?;
        match native(self.writer.progress(&admission))? {
            Progress::Completed(result) | Progress::Cancelled(result) => return Ok(result),
            Progress::Prepared(_) => return native(self.writer.prepared(&admission)),
            Progress::Absent => (),
            _ => return Err(invalid()),
        }
        review.after.validate(self.identity)?;
        if state_digest(&self.snapshot()?)? != review.before_digest {
            return Err(invalid());
        }
        for effect in &review.effects {
            let current = effect.locator.observe()?;
            if current.before != effect.observation || current.value != effect.before {
                return Err(invalid());
            }
        }
        native(self.writer.prepare(&admission, &review.value()?, &[]))
    }
    pub fn start(&self, review: &Review) -> Result<()> {
        self.private_root()?;
        for effect in &review.effects {
            let current = effect.locator.observe()?;
            if current.before != effect.observation || current.value != effect.before {
                return Err(invalid());
            }
        }
        native(self.writer.start(&Self::admission(review)?))
    }
    /// Recover the original pending review even when the caller's plan file or
    /// last reply was lost. This returns data, without applying configuration.
    pub fn pending(&self) -> Result<Option<Review>> {
        self.private_root()?;
        let Some((admission, context)) = native(self.writer.pending())? else {
            return Ok(None);
        };
        let review = Review::parse(&encode(&context)?, &admission.plan_digest)?;
        if Self::admission(&review)? != admission {
            return Err(invalid());
        }
        Ok(Some(review))
    }

    pub fn status(&self, review: &Review) -> Result<Value> {
        self.private_root()?;
        let admission = Self::admission(review)?;
        let (state, result) = match native(self.writer.progress(&admission))? {
            Progress::Absent => ("absent", None),
            Progress::Prepared(_) => ("prepared", None),
            Progress::Applying(_) => ("applying", None),
            Progress::Finishing => ("finishing", None),
            Progress::Completed(value) => ("completed", Some(value)),
            Progress::Cancelled(value) => ("cancelled", Some(value)),
        };
        Ok(
            json!({"operation_id":review.operation_id,"review_digest":admission.plan_digest,"state":state,"result":result,"authorization_granted":false}),
        )
    }

    pub fn cancel(&mut self, review: &Review) -> Result<Value> {
        native(self.writer.cancel(&Self::admission(review)?))
    }
    pub fn complete(&mut self, review: &Review) -> Result<Value> {
        self.private_root()?;
        let admission = Self::admission(review)?;
        match native(self.writer.progress(&admission))? {
            Progress::Completed(value) => return Ok(value),
            Progress::Applying(_) | Progress::Finishing => (),
            _ => return Err(invalid()),
        }
        for effect in &review.effects {
            if effect.locator.observe()?.value != effect.after {
                return Err(invalid());
            }
        }
        match native(self.writer.progress(&admission))? {
            Progress::Applying(_) => {
                let mut after = review.after.clone();
                let mut touched = Vec::new();
                for effect in &review.effects {
                    let (parent, remaining, file) = effect
                        .observation
                        .address(effect.locator.root.identity, &effect.locator.path);
                    touched.push(model::Address {
                        parent,
                        remaining,
                        file,
                    });
                    touched.push(effect.locator.observe()?.address);
                }
                for entry in &mut after.entries {
                    if !touched
                        .iter()
                        .any(|address| address.same_file(&entry.address))
                    {
                        continue;
                    }
                    let observed = entry
                        .references
                        .values()
                        .next()
                        .ok_or_else(invalid)?
                        .locator
                        .observe()?;
                    if observed.value.as_ref() != Some(&entry.value) {
                        return Err(invalid());
                    }
                    entry.address = observed.address;
                }
                after.validate(self.identity)?;
                let change = native(self.writer.change(
                    STATE,
                    Some(native(forward::Content::new(encode(&after)?, 0o600))?),
                ))?;
                let result = json!({"schema_version":1,"kind":"native.custody.commit","operation_id":review.operation_id,"review_digest":admission.plan_digest,"revision":after.revision,"claim_count":after.entries.len(),"authorization_granted":false});
                native(self.writer.finish(&admission, &[change], &result))?;
            }
            Progress::Finishing => (),
            _ => return Err(invalid()),
        }
        native(self.writer.apply(&admission))?;
        native(self.writer.complete(&admission))
    }
}
