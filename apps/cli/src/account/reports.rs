//! Explicit reporter previews and durable delivery of one exact request.

pub(super) mod contract;

use super::{access::Access, transport::Code};
use crate::{
    digest,
    error::{ErrorKind, Failure, Result},
    files::{self, OwnedDirectory},
    identity, passport, wire,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::Path;

const LIMIT: u64 = 65536;
const DIRECTORY: &str = "ai-stp-v2-reports";
const OWNER: &[u8] = b"ai-stp-cli-v2 report delivery v1\n";

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Record {
    schema_version: u32,
    plan_id: String,
    account_id: String,
    origin: String,
    root_identity: [String; 2],
    request: Value,
    request_sha256: String,
    created_at: String,
    started: bool,
    submitted: Option<Value>,
}

pub(super) fn invalid() -> Failure {
    Failure::input("the report request, retained preview or response is invalid")
}

pub(super) fn uncertain() -> Failure {
    Failure::new(
        ErrorKind::Unavailable,
        "report delivery was not confirmed; retry the retained preview and exact digest",
    )
}

pub(super) fn refusal(code: Code) -> Failure {
    let kind = match code {
        Code::Conflict => ErrorKind::Conflict,
        Code::NotFound => ErrorKind::NotFound,
        Code::Invalid => ErrorKind::Input,
        Code::SlowDown => ErrorKind::Unavailable,
        _ => ErrorKind::Precondition,
    };
    Failure::new(kind, "the account API refused the report request")
}

fn encode(value: &impl Serialize) -> Result<Vec<u8>> {
    let bytes = serde_json::to_vec(value).map_err(|_| invalid())?;
    if bytes.len() as u64 > LIMIT {
        return Err(invalid());
    }
    Ok(bytes)
}

fn key(account: &str, origin: &str, caller: &str) -> Result<String> {
    Ok(digest::sha256(&contract::bytes(&json!([
        "ai-stp-native-report/1",
        account,
        origin,
        caller
    ]))?))
}

fn plan_id(key: &str) -> Result<String> {
    let number =
        u128::from_str_radix(key.get(7..39).ok_or_else(invalid)?, 16).map_err(|_| invalid())?;
    Ok(format!("plan_{}", ulid::Ulid::from(number)))
}

impl Record {
    fn validate(&self) -> Result<()> {
        contract::validate(&self.request)?;
        if self.schema_version != 1
            || !passport::stable_id(&self.account_id, "account")
            || super::transport::origin(&self.origin)? != self.origin
            || !passport::timestamp(&self.created_at)
            || self.request_sha256 != digest::sha256(&contract::bytes(&self.request)?)
            || self.plan_id
                != plan_id(&key(
                    &self.account_id,
                    &self.origin,
                    contract::text(&self.request, "idempotency_key")?,
                )?)?
            || self.submitted.is_some() && !self.started
        {
            return Err(invalid());
        }
        if let Some(submitted) = &self.submitted
            && contract::bound(submitted, &self.request)? != *submitted
        {
            return Err(invalid());
        }
        Ok(())
    }

    fn digest(&self) -> Result<String> {
        self.validate()?;
        digest::canonical(
            "ai-stp:plan:v1",
            &json!({"schema_version":1,
            "plan_id":self.plan_id,"account_id":self.account_id,"api_origin":self.origin,
            "root_identity":self.root_identity,"request_sha256":self.request_sha256,
            "created_at":self.created_at}),
        )
    }

    fn body(&self) -> Result<Value> {
        let mut body = self.request.clone();
        // The server replays solely by account/key, without a payload hash.
        // Bind this client's wire key to every original byte and its origin.
        let hash = key(&self.account_id, &self.origin, &self.request_sha256)?;
        body["idempotency_key"] = format!("native.report.{}", &hash[7..]).into();
        Ok(body)
    }

    fn preview(&self) -> Result<Value> {
        Ok(
            json!({"schema_version":1,"plan_id":self.plan_id,"plan_digest":self.digest()?,
            "account_id":self.account_id,"api_origin":self.origin,"created_at":self.created_at,
            "report":self.body()?,"submitted":self.submitted.is_some()}),
        )
    }
}

fn directory(identity: &identity::Identity, create: bool) -> Result<OwnedDirectory> {
    OwnedDirectory::open_at(identity.root_directory(), DIRECTORY, OWNER, create)?
        .ok_or_else(|| Failure::new(ErrorKind::NotFound, "the report preview is absent"))
}

fn load(dir: &OwnedDirectory, id: &str) -> Result<Option<Record>> {
    if !passport::stable_id(id, "plan") {
        return Err(invalid());
    }
    let Some(bytes) = dir.read_file(&format!("{id}.json"), LIMIT)? else {
        return Ok(None);
    };
    let record: Record = serde_json::from_value(wire::parse(&bytes)?).map_err(|_| invalid())?;
    record.validate()?;
    if record.plan_id != id {
        return Err(invalid());
    }
    Ok(Some(record))
}

fn retained(
    dir: &OwnedDirectory,
    identity: &identity::Identity,
    id: &str,
    expected: &str,
) -> Result<Record> {
    let record = load(dir, id)?
        .ok_or_else(|| Failure::new(ErrorKind::NotFound, "the report preview is absent"))?;
    if record.digest()? != expected || &record.root_identity != identity.root_binding().1 {
        return Err(invalid());
    }
    Ok(record)
}

pub fn preview(root: &Path, origin: Option<&str>, input: &Path, at: &str) -> Result<Value> {
    let request = contract::prepare(wire::parse(&files::read(input, LIMIT)?)?)?;
    let access = Access::for_account(root, origin)?;
    let identity = super::identity_at(root)?;
    let dir = directory(&identity, true)?;
    let account = access.binding();
    let id = plan_id(&key(
        &account.account_id,
        &account.origin,
        contract::text(&request, "idempotency_key")?,
    )?)?;
    let hash = digest::sha256(&contract::bytes(&request)?);
    if let Some(record) = load(&dir, &id)? {
        if record.account_id != account.account_id
            || record.origin != account.origin
            || record.root_identity != account.root_identity
            || record.request_sha256 != hash
        {
            return Err(Failure::new(
                ErrorKind::Conflict,
                "the report key already belongs to a different exact preview",
            ));
        }
        return record.preview();
    }
    let record = Record {
        schema_version: 1,
        plan_id: id,
        account_id: account.account_id.clone(),
        origin: account.origin.clone(),
        root_identity: account.root_identity.clone(),
        request,
        request_sha256: hash,
        created_at: at.into(),
        started: false,
        submitted: None,
    };
    let view = record.preview()?;
    access.revalidate()?;
    dir.atomic(&format!("{}.json", record.plan_id), &encode(&record)?)?;
    Ok(view)
}

pub fn confirm(root: &Path, id: &str, expected: &str, confirmed: bool) -> Result<Value> {
    if !confirmed {
        return Err(Failure::precondition(
            "report delivery requires explicit --confirm of the exact preview digest",
        ));
    }
    let identity = super::identity_at(root)?;
    let record = {
        let dir = directory(&identity, false)?;
        retained(&dir, &identity, id, expected)?
    };
    if let Some(case) = record.submitted {
        return Ok(json!({"schema_version":1,"historical":true,"case":case}));
    }
    // Lock order stays account then reporter journal. A completed receipt above
    // remains readable after logout and never acquires network authority.
    let mut access = Access::for_account(root, Some(&record.origin))?;
    if access.binding().account_id != record.account_id
        || access.binding().root_identity != record.root_identity
    {
        return Err(invalid());
    }
    access.verify()?;
    let dir = directory(&identity, false)?;
    let mut record = retained(&dir, &identity, id, expected)?;
    if let Some(case) = record.submitted {
        return Ok(json!({"schema_version":1,"historical":true,"case":case}));
    }
    record.started = true;
    dir.atomic(&format!("{id}.json"), &encode(&record)?)?;
    let response = access.reports(None, None, Some(&contract::bytes(&record.body()?)?))?;
    let case = contract::bound(&response, &record.request).map_err(|_| uncertain())?;
    record.submitted = Some(case.clone());
    access.revalidate()?;
    dir.atomic(&format!("{id}.json"), &encode(&record)?)?;
    Ok(json!({"schema_version":1,"historical":false,"case":case}))
}

pub fn list(root: &Path, origin: Option<&str>, cursor: Option<&str>) -> Result<Value> {
    if cursor.is_some_and(|value| !contract::cursor(value)) {
        return Err(invalid());
    }
    let mut access = Access::for_account(root, origin)?;
    access.verify()?;
    let value = access.reports(None, cursor, None)?;
    let page = contract::page(&value, cursor)?;
    Ok(
        json!({"schema_version":1,"account_id":access.binding().account_id,
        "api_origin":access.binding().origin,"source":"online","response":page}),
    )
}

pub fn status(root: &Path, origin: Option<&str>, id: &str) -> Result<Value> {
    if !passport::stable_id(id, "report") {
        return Err(invalid());
    }
    let mut access = Access::for_account(root, origin)?;
    access.verify()?;
    let case = contract::case(&access.reports(Some(id), None, None)?)?;
    if case["case_id"] != id {
        return Err(invalid());
    }
    Ok(
        json!({"schema_version":1,"account_id":access.binding().account_id,
        "api_origin":access.binding().origin,"source":"online","case":case}),
    )
}
