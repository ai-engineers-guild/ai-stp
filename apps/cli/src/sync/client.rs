//! Held account before registry; durable requests and pages surround HTTP.

use rusqlite::{OptionalExtension, params};
use serde_json::{Value, json};
use std::{collections::BTreeSet, path::Path};

use crate::{
    account::access::Access,
    authoring::runtime::{self, Owner},
    config,
    error::{Failure, Result},
    store::Store,
};

use super::{
    event::Event,
    ledger::{self, Scope},
    network::Request,
    pages,
};

pub struct Client {
    // Release the registry before its owner capability and account lock.
    pub(super) store: Store,
    _owner: Owner,
    account: Access,
    pub(super) scope: Scope,
    pub(super) run: Option<super::run::Run>,
}

pub(super) fn enabled(configuration: Option<&Path>) -> Result<()> {
    let settings = config::show(configuration, &[])?;
    if !settings["values"].as_array().is_some_and(|values| {
        values
            .iter()
            .any(|v| v["path"] == "sync.enabled" && v["value"] == true)
    }) {
        return Err(Failure::precondition(
            "private sync is disabled; explicit sync.enabled=true is required",
        ));
    }
    Ok(())
}

impl Client {
    pub fn open(root: &Path, origin: Option<&str>, configuration: Option<&Path>) -> Result<Self> {
        Self::open_bound(root, origin, configuration, None)
    }

    pub(super) fn for_plan(
        root: &Path,
        configuration: Option<&Path>,
        plan: &super::runtime::Plan,
    ) -> Result<Self> {
        Self::open_bound(root, Some(&plan.account.origin), configuration, Some(plan))
    }

    fn open_bound(
        root: &Path,
        origin: Option<&str>,
        configuration: Option<&Path>,
        plan: Option<&super::runtime::Plan>,
    ) -> Result<Self> {
        enabled(configuration)?;
        let mut account = match plan {
            Some(plan) => Access::for_binding(root, &plan.account, false)?,
            None => Access::for_account(root, origin)?,
        };
        if plan.is_some_and(|expected| &expected.account != account.binding()) {
            return Err(Failure::precondition(
                "the sync account, session, device or physical root changed after planning",
            ));
        }
        account.verify()?;
        let owner = runtime::owner(root)?;
        let planned = owner.planning()?;
        account.check_registry_owner(&planned.connection)?;
        drop(planned);
        let scope = Scope::new(&account.binding().account_id, &account.binding().origin)?;
        if let Some(plan) = plan {
            let store = owner.planning()?;
            plan.validate_local(
                &store.connection,
                &owner,
                &scope,
                &format!("{:.3}", jiff::Timestamp::now()),
            )?;
        }
        let mut store = owner.open(true)?;
        // Recheck under the retained writer lease. The command admits its origin
        // and operation together, only after all query-only preconditions pass.
        if let Some(plan) = plan {
            plan.validate_local(
                &store.connection,
                &owner,
                &scope,
                &format!("{:.3}", jiff::Timestamp::now()),
            )?;
        } else {
            store.transaction(|t| scope.bind(t, &format!("{:.3}", jiff::Timestamp::now())))?;
        }
        Ok(Self {
            store,
            _owner: owner,
            account,
            scope,
            run: None,
        })
    }

    /// The higher-level push walk supplies a sealed candidate from local state.
    /// Retention settles any older uncertain event before admitting a new one.
    pub fn deliver(&mut self, request: &Value) -> Result<Value> {
        self.account.revalidate()?;
        let event = Event::push(request, self.scope.account())?;
        if event.device_id != self.account.binding().device_id {
            return Err(Failure::precondition(
                "the sync event belongs to another signing device; plan explicit recovery before another push",
            ).with_details([("event_id".into(),event.event_id.into()),("next_command_path".into(),"sync recover plan".into())]));
        }
        let held = self.store.transaction(|t| {
            if let Some(run) = &self.run {
                run.check(t, &self.scope)?;
            }
            let held = ledger::retain(t, &self.scope, request)?;
            if let Some(run) = &mut self.run {
                run.save(
                    t,
                    &self.scope,
                    None,
                    &format!("{:.3}", jiff::Timestamp::now()),
                )?;
            }
            Ok(held)
        })?;
        if held.state == "failed" {
            return Err(Failure::precondition(
                "a locally retired request cannot be delivered again",
            ));
        }
        if let Some(receipt) = held.receipt {
            return Ok(receipt);
        }
        let body = json!({"schema_version":1,"events":[held.request]});
        // No Transaction exists during this call. A lost reply leaves the exact
        // retained request pending; this layer never performs an automatic retry.
        let response = self.account.sync(&Request::Push(&body))?;
        let receipt = response["receipts"]
            .as_array()
            .and_then(|r| r.first())
            .ok_or_else(super::network::invalid)?;
        self.store.transaction(|t| {
            if let Some(run) = &self.run {
                run.check(t, &self.scope)?;
            }
            ledger::record_receipt(t, &self.scope, receipt)?;
            if let Some(run) = &mut self.run {
                run.save(
                    t,
                    &self.scope,
                    None,
                    &format!("{:.3}", jiff::Timestamp::now()),
                )?;
            }
            Ok(())
        })?;
        Ok(receipt.clone())
    }

    pub fn pull(&mut self, page_size: u16, skip: &BTreeSet<String>) -> Result<Value> {
        self.account.revalidate()?;
        let cursor = self.store.transaction(|t| {
            if let Some(run) = &self.run {
                run.check(t, &self.scope)?;
            }
            pages::cursor(t, &self.scope)
        })?;
        let response = self.account.sync(&Request::Pull {
            cursor: cursor.as_deref(),
            page_size,
        })?;
        self.store.transaction(|t| {
            if let Some(run) = &self.run {
                run.check(t, &self.scope)?;
            }
            let at = format!("{:.3}", jiff::Timestamp::now());
            let result = pages::apply_transaction(
                t,
                &self.scope,
                &response,
                cursor.as_deref(),
                page_size,
                skip,
                &at,
            )?;
            if let Some(run) = &mut self.run {
                run.save(t, &self.scope, Some(result.clone()), &at)?;
            }
            Ok(result)
        })
    }

    pub fn capture_push(&mut self, id: &str) -> Result<super::push::Capture> {
        self.account.revalidate()?;
        let sender = crate::authoring::Identity {
            account_id: self.account.binding().account_id.clone(),
            device_id: self.account.binding().device_id.clone(),
        };
        self.store
            .transaction(|t| super::push::capture_for_sender(t, &self._owner, &sender, id))
    }

    pub(super) fn recover(
        &mut self,
        capture: &super::recovery::Capture,
        operation_id: &str,
        digest: &str,
    ) -> Result<Value> {
        self.account.revalidate()?;
        let run = self.run.as_mut().ok_or_else(|| {
            Failure::precondition("sync recovery requires an admitted exact command")
        })?;
        self.store.transaction(|t| {
            run.check(t, &self.scope)?;
            let result = super::recovery::retire(t, &self.scope, capture, operation_id, digest)?;
            run.save(
                t,
                &self.scope,
                Some(result.clone()),
                &format!("{:.3}", jiff::Timestamp::now()),
            )?;
            Ok(result)
        })
    }

    fn sent(&mut self, request: &Value, history: &mut super::push::History) -> Result<Value> {
        let receipt = self.deliver(request)?;
        let (stored,head)=self.store.transaction(|t| {
            let stored=ledger::recorded(t,&self.scope,receipt["event_id"].as_str().ok_or_else(super::network::invalid)?)?;
            let head=t.query_row("SELECT remote_revision_id FROM sync_remote_head WHERE account_id=? AND entity_id=?",
                params![self.scope.account(),request["entity_id"].as_str()],|r|r.get(0)).optional().map_err(crate::store::database)?;
            Ok((stored,head))
        })?;
        history.update(stored, head)?;
        Ok(receipt)
    }

    /// The runtime's exact operation plan owns confirmation. This capture binds
    /// every local payload, version closure and deletion mark before delivery.
    pub fn push(&mut self, capture: &super::push::Capture, expected: &str) -> Result<Value> {
        use super::push;
        if capture.digest()? != expected || self.capture_push(&capture.entity_id)? != *capture {
            return Err(Failure::precondition(
                "the local private push changed after capture",
            ));
        }
        let mut history = self
            .store
            .transaction(|t| push::History::load(t, &self.scope, &capture.entity_id))?;
        let mut processed = 0;
        let sender = crate::authoring::Identity {
            account_id: self.account.binding().account_id.clone(),
            device_id: self.account.binding().device_id.clone(),
        };
        // Settle an older uncertain generation before asking the graph for a
        // new event. Retired-device requests remain explicit refusals; they are
        // never re-signed or overwritten under another device's credentials.
        if let Some(pending) = history.pending() {
            let request = pending.stored.request.clone();
            let receipt = self.sent(&request, &mut history)?;
            processed += 1;
            if receipt["state"] == "rejected" {
                return Ok(push::outcome(capture, &receipt, processed));
            }
        }
        let mut last = None;
        for (index, step) in capture.steps.iter().enumerate() {
            let is_head = index + 1 == capture.steps.len();
            let receipt = if let Some(known) = history.known(step, is_head) {
                push::receipt(known)
            } else {
                let request = history.request(capture, step, &sender)?;
                self.sent(&request, &mut history)?
            };
            processed += 1;
            let state = receipt["state"]
                .as_str()
                .ok_or_else(super::network::invalid)?;
            if state != "accepted" && (is_head || state == "rejected") {
                return Ok(push::outcome(capture, &receipt, processed));
            }
            last = Some(receipt);
        }
        if let Some(step) = push::tombstone(capture) {
            let receipt = if let Some(known) = history.known(&step, true) {
                push::receipt(known)
            } else {
                let request = history.request(capture, &step, &sender)?;
                self.sent(&request, &mut history)?
            };
            processed += 1;
            last = Some(receipt);
        }
        Ok(push::outcome(
            capture,
            &last.ok_or_else(super::network::invalid)?,
            processed,
        ))
    }
}
