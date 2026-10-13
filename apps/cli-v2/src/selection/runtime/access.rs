//! Explicit local trust decisions and fresh exact catalog access are separate.
//! Neither is a new owner, a verification flag or a durable authorization cache.

use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
};

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{Inputs, Owner, graph, text};
use crate::{
    account::{
        access::{Access, Binding},
        attachment,
    },
    authoring::setups::Source,
    catalog::acquisition,
    digest,
    error::{Failure, Result},
    files,
    objects::Objects,
    wire,
};

#[derive(Clone, Default, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub(super) struct Request {
    #[serde(default, skip_serializing_if = "BTreeSet::is_empty")]
    trust_pins: BTreeSet<String>,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    account: bool,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Plan {
    request: Request,
    account: Option<Binding>,
}

pub(super) enum Intent<'a> {
    Review(&'a Request),
    Apply(Option<&'a Plan>),
}

fn invalid() -> Failure {
    Failure::input(
        "selection access requires at most 512 exact passport trust pins and explicit account access",
    )
}

impl Request {
    pub fn read(path: Option<&Path>) -> Result<Self> {
        let request = path
            .map(|path| {
                serde_json::from_value(wire::parse(&files::read(path, 64 * 1024)?)?)
                    .map_err(|_| invalid())
            })
            .transpose()?
            .unwrap_or_default();
        Self::validate(&request)?;
        Ok(request)
    }

    pub fn validate(&self) -> Result<()> {
        if self.trust_pins.len() > 512
            || self.trust_pins.iter().any(|pin| {
                !pin.strip_prefix("sha256:").is_some_and(|value| {
                    value.len() == 64
                        && value
                            .bytes()
                            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
                })
            })
        {
            return Err(invalid());
        }
        Ok(())
    }

    pub fn is_empty(&self) -> bool {
        self.trust_pins.is_empty() && !self.account
    }

    pub fn planned(plan: Option<&Plan>) -> Result<Self> {
        if let Some(plan) = plan {
            plan.validate()?;
            Ok(plan.request.clone())
        } else {
            Ok(Self::default())
        }
    }
}

impl Plan {
    fn validate(&self) -> Result<()> {
        self.request.validate()?;
        if self.request.is_empty() || self.request.account != self.account.is_some() {
            return Err(invalid());
        }
        if let Some(binding) = &self.account {
            binding.validate()?;
        }
        Ok(())
    }
}

/// The account journal remains locked until the caller completes its registry
/// observation or effect. Load before taking a registry lock, never from SQL.
pub(super) struct Observed {
    request: Request,
    account: Option<Access>,
    authorized: BTreeSet<String>,
    context_digest: Option<String>,
    checked_at: Option<String>,
}

impl Observed {
    pub fn capture(
        parent: &Path,
        owner: &Owner,
        groups: &[Vec<Value>],
        intent: Intent<'_>,
    ) -> Result<Self> {
        let (request, expected) = match intent {
            Intent::Review(request) => (request.clone(), None),
            Intent::Apply(plan) => (Request::planned(plan)?, plan),
        };
        request.validate()?;
        let mut account = request
            .account
            .then(|| Access::for_account(parent, None))
            .transpose()?;
        if let Some(expected) = expected
            && expected.account.as_ref() != account.as_ref().map(Access::binding)
        {
            return Err(Failure::precondition(
                "the selection account, device, session or origin changed after planning",
            ));
        }
        let mut known = BTreeSet::new();
        let mut private = BTreeMap::new();
        if !request.is_empty() {
            let mut store = owner.planning()?;
            store.transaction(|connection| {
                let inherited = attachment::inherited(connection, &owner.account_id)?;
                for roots in groups {
                    if roots.is_empty() {
                        continue;
                    }
                    let closure = graph::exact(connection, roots)?;
                    if closure["resolved"] != true {
                        continue;
                    }
                    for node in closure["nodes"].as_array().ok_or_else(invalid)? {
                        let address = text(node, "passport_digest")?;
                        known.insert(address.to_owned());
                        if !request.account || inherited.contains(address) {
                            continue;
                        }
                        let id = text(node, "stable_id")?;
                        let version = text(node, "version")?;
                        let document =
                            Objects { connection }.exact_version(id, version, Some(address))?;
                        if document["owner_id"] != owner.account_id
                            && document["visibility"] != "public"
                        {
                            private.insert(
                                address.to_owned(),
                                Source {
                                    stable_id: id.into(),
                                    version: version.into(),
                                    passport_digest: address.into(),
                                },
                            );
                        }
                    }
                }
                Ok(())
            })?;
        }
        if !request.trust_pins.is_subset(&known) {
            return Err(Failure::precondition(
                "a trust pin is outside the resolved exact candidate graphs; narrow the pins or resolve the graph",
            ));
        }
        let authorized = if let Some(account) = &mut account {
            acquisition::authorize_versions(account, &private.into_values().collect::<Vec<_>>())?
        } else {
            BTreeSet::new()
        };
        let context_digest = account
            .as_ref()
            .map(|account| {
                let mut binding = serde_json::to_value(account.binding()).map_err(|_| invalid())?;
                // Outer plans bind the full session revision. Proposal policy keeps
                // the account/device context across an explicit same-account refresh.
                binding
                    .as_object_mut()
                    .ok_or_else(invalid)?
                    .remove("revision");
                digest::canonical("ai-stp:plan:v1", &binding)
            })
            .transpose()?;
        let checked_at = account
            .as_ref()
            .map(|_| format!("{:.3}", jiff::Timestamp::now()));
        let observed = Self {
            request,
            account,
            authorized,
            context_digest,
            checked_at,
        };
        observed.revalidate()?;
        Ok(observed)
    }

    pub fn revalidate(&self) -> Result<()> {
        self.account.as_ref().map(Access::revalidate).transpose()?;
        Ok(())
    }

    pub fn plan(&self) -> Result<Option<Plan>> {
        self.revalidate()?;
        Ok((!self.request.is_empty()).then(|| Plan {
            request: self.request.clone(),
            account: self
                .account
                .as_ref()
                .map(|account| account.binding().clone()),
        }))
    }

    pub fn apply(&self, inputs: &mut Inputs) -> Result<()> {
        self.revalidate()?;
        if self.request.is_empty() {
            return Ok(());
        }
        let exact = inputs
            .evidence
            .values()
            .map(|e| e.passport_digest.clone())
            .collect::<BTreeSet<_>>();
        inputs.target.pinned_passport_digests = self
            .request
            .trust_pins
            .intersection(&exact)
            .cloned()
            .collect();
        inputs.target.accessible_passport_digests =
            self.authorized.intersection(&exact).cloned().collect();
        inputs
            .target
            .access_context_digest
            .clone_from(&self.context_digest);
        inputs.target.validate()
    }

    pub fn report(&self) -> Result<Option<Value>> {
        self.revalidate()?;
        Ok((!self.request.is_empty()).then(|| {
            json!({
                "schema_version":1,"trust_pins":self.request.trust_pins,
                "account_id":self.account.as_ref().map(|account| &account.binding().account_id),
                "api_origin":self.account.as_ref().map(|account| &account.binding().origin),
                "checked_at":self.checked_at,"authorized_passport_digests":self.authorized
            })
        }))
    }
}
