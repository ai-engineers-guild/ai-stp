//! Held account before registry; durable requests and pages surround HTTP.

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
    store: Store,
    _owner: Owner,
    account: Access,
    scope: Scope,
}

impl Client {
    pub fn open(root: &Path, origin: Option<&str>, configuration: Option<&Path>) -> Result<Self> {
        let settings = config::show(configuration, &[])?;
        if !settings["values"].as_array().is_some_and(|values| {
            values
                .iter()
                .any(|value| value["path"] == "sync.enabled" && value["value"] == true)
        }) {
            return Err(Failure::precondition(
                "private sync is disabled; explicit sync.enabled=true is required",
            ));
        }
        let mut account = Access::for_account(root, origin)?;
        account.verify()?;
        let owner = runtime::owner(root)?;
        if owner.account_id != account.binding().account_id
            || owner.device_id != account.binding().device_id
        {
            return Err(Failure::precondition(
                "private sync requires the unchanged attached account and device",
            ));
        }
        let mut store = owner.open(true)?;
        let scope = Scope::new(&account.binding().account_id, &account.binding().origin)?;
        store.transaction(|t| scope.bind(t, &format!("{:.3}", jiff::Timestamp::now())))?;
        Ok(Self {
            store,
            _owner: owner,
            account,
            scope,
        })
    }

    /// The higher-level push walk supplies a sealed candidate from local state.
    /// Retention settles any older uncertain event before admitting a new one.
    pub fn deliver(&mut self, request: &Value) -> Result<Value> {
        self.account.revalidate()?;
        let event = Event::push(request, self.scope.account())?;
        if event.device_id != self.account.binding().device_id {
            return Err(Failure::precondition(
                "the sync event belongs to another signing device",
            ));
        }
        let held = self
            .store
            .transaction(|t| ledger::retain(t, &self.scope, request))?;
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
        self.store
            .transaction(|t| ledger::record_receipt(t, &self.scope, receipt))?;
        Ok(receipt.clone())
    }

    pub fn pull(&mut self, page_size: u16, skip: &BTreeSet<String>) -> Result<Value> {
        self.account.revalidate()?;
        let cursor = self.store.transaction(|t| pages::cursor(t, &self.scope))?;
        let response = self.account.sync(&Request::Pull {
            cursor: cursor.as_deref(),
            page_size,
        })?;
        pages::apply(
            &mut self.store,
            &self.scope,
            &response,
            cursor.as_deref(),
            page_size,
            skip,
            &format!("{:.3}", jiff::Timestamp::now()),
        )
    }
}
