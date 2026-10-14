//! One bounded API exchange at a time. The caller owns durable admission and
//! continuation; this client never invents retries, keys or terminal publication.

use std::path::Path;

use serde_json::Value;

use super::contract::Create;
use crate::{
    account::access::{Access, Binding},
    digest,
    error::{ErrorKind, Failure, Result},
};

pub struct Client {
    access: Access,
}

pub(crate) enum Request<'a> {
    Create(&'a Create),
    Status(&'a str),
    Bind {
        plan_id: &'a str,
        projection: Option<&'a str>,
        payload: &'a [u8],
    },
    Confirm {
        plan_id: &'a str,
        body: &'a Value,
    },
}

pub(crate) fn uncertain() -> Failure {
    Failure::new(
        ErrorKind::Unavailable,
        "the publication response was not confirmed; retain the original request and idempotency key for reconciliation",
    )
}

impl Client {
    /// Acquire the account before opening the registry. Callers must release
    /// their SQLite transaction before invoking any exchange below.
    pub fn connect(root: &Path, origin: Option<&str>) -> Result<Self> {
        Ok(Self {
            access: Access::for_account(root, origin)?,
        })
    }

    pub fn binding(&self) -> &Binding {
        self.access.binding()
    }

    pub fn catalog(
        &mut self,
        snapshot: &super::Snapshot,
        visibility: super::contract::Visibility,
    ) -> Result<Option<super::readback::Observation>> {
        super::readback::read(&mut self.access, snapshot, visibility)
    }

    pub(super) fn authorize(&mut self, request: &Create, write: bool) -> Result<()> {
        request.validate()?;
        let held = self.access.binding();
        let expected = &request.account;
        if held.account_id != expected.account_id
            || held.origin != expected.origin
            || held.root_identity != expected.root_identity
            || write
                && (held.device_id != expected.device_id
                    || held.public_key != expected.public_key
                    || held.credential_store != expected.credential_store)
        {
            return Err(Failure::precondition(
                "publication belongs to another account, origin, root or device",
            ));
        }
        // A refreshed session can carry the original body/key. Its outer plan
        // must bind this current session revision before admission by the caller.
        self.access.verify()
    }

    pub(super) fn registry(&self) -> Result<crate::store::Store> {
        self.access.publication_registry()
    }

    fn exchange(
        &self,
        request: &Create,
        previous: Option<&Value>,
        wire: Request<'_>,
    ) -> Result<Value> {
        let result = self.access.publication(&wire)?;
        request
            .response(&result, previous)
            .map_err(|_| uncertain())?;
        Ok(result)
    }

    /// The original request must already be durable before this first write.
    pub fn create(&mut self, request: &Create) -> Result<Value> {
        self.authorize(request, true)?;
        self.exchange(request, None, Request::Create(request))
    }

    /// Same-account observation can settle an old device's known plan. Reading
    /// its result never authorizes a new write with that retired device.
    pub fn status(&mut self, request: &Create, previous: &Value) -> Result<Value> {
        request.response(previous, None)?;
        self.authorize(request, false)?;
        self.exchange(
            request,
            Some(previous),
            Request::Status(super::text(previous, "plan_id")?),
        )
    }

    pub fn bind(
        &mut self,
        request: &Create,
        plan: &Value,
        projection: Option<&str>,
        payload: &[u8],
    ) -> Result<Value> {
        request.response(plan, None)?;
        let address = projection.unwrap_or(super::text(request.body(), "content_digest")?);
        let artifacts = request.artifacts()?;
        let size = artifacts
            .get(address)
            .ok_or_else(|| Failure::input("publication does not declare that artifact"))?;
        if payload.len() != *size || digest::bytes("ai-stp:artifact:v1", payload)? != address {
            return Err(Failure::precondition(
                "publication payload differs from its sealed digest or length",
            ));
        }
        // The separate projection route accepts only scope declarations. The
        // original may equal a projection, but a setup has no projection route.
        if let Some(address) = projection {
            let declared = request.body()["passport"]["adaptations"]
                .as_array()
                .into_iter()
                .flatten()
                .flat_map(|a| a["scope_adaptations"].as_array().into_iter().flatten())
                .any(|s| s["projection_artifact"]["digest"] == address);
            if !declared {
                return Err(Failure::input(
                    "publication does not declare that projection",
                ));
            }
        }
        self.authorize(request, true)?;
        self.exchange(
            request,
            Some(plan),
            Request::Bind {
                plan_id: super::text(plan, "plan_id")?,
                projection,
                payload,
            },
        )
    }

    /// Persist this exact confirmation key before calling. A returned queued
    /// state still requires the worker and exact catalog readback.
    pub fn confirm(&mut self, request: &Create, plan: &Value, key: &str) -> Result<Value> {
        let body = request.confirmation(plan, key)?;
        self.authorize(request, true)?;
        self.exchange(
            request,
            Some(plan),
            Request::Confirm {
                plan_id: super::text(plan, "plan_id")?,
                body: &body,
            },
        )
    }
}

impl Request<'_> {
    pub(crate) fn url(&self, origin: &str) -> Result<String> {
        let mut url =
            url::Url::parse(origin).map_err(|_| Failure::input("invalid publication origin"))?;
        {
            let mut path = url
                .path_segments_mut()
                .map_err(|_| Failure::input("invalid publication origin"))?;
            path.clear().extend(["v1", "publications", "plans"]);
            let id = match self {
                Self::Create(_) => None,
                Self::Status(id)
                | Self::Bind { plan_id: id, .. }
                | Self::Confirm { plan_id: id, .. } => Some(*id),
            };
            if let Some(id) = id {
                if !(8..=64).contains(&id.chars().count()) {
                    return Err(Failure::input("invalid publication plan identifier"));
                }
                path.push(id);
            }
            match self {
                Self::Bind {
                    projection: None, ..
                } => {
                    path.push("artifact");
                }
                Self::Bind {
                    projection: Some(address),
                    ..
                } => {
                    path.extend(["artifacts", address]);
                }
                Self::Confirm { .. } => {
                    path.push("confirm");
                }
                _ => {}
            }
        }
        Ok(url.into())
    }
}
