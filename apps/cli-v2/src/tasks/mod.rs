//! Durable agent tasks call native services in-process and retain exact child plans.

mod claim;
mod input;
mod install;
mod journal;
mod service;
#[cfg(test)]
mod tests;

use std::path::Path;

use serde_json::{Value, json};

use crate::{
    authoring::{embedded, runtime},
    error::{ErrorKind, Failure, Result},
    store::Store,
};
use journal::Row;

pub const INTENTS: &[&str] = &["author", "install"];

fn valid_key(key: &str) -> Result<()> {
    if !(16..=128).contains(&key.len())
        || !key
            .bytes()
            .all(|v| v.is_ascii_alphanumeric() || b"._~-".contains(&v))
    {
        return Err(Failure::input(
            "idempotency key must be 16 to 128 ASCII letters, digits, '.', '_', '~' or '-'",
        ));
    }
    Ok(())
}

fn moment() -> String {
    format!("{:.3}", jiff::Timestamp::now())
}

pub fn intents() -> Result<Value> {
    Ok(
        json!({"schema_version":1,"cli_version":crate::registry::VERSION,"registry_digest":crate::registry::digest()?,
        "intents":[input::descriptor()?,install::descriptor()?]}),
    )
}

pub fn input_schema(intent: &str) -> Result<Value> {
    match intent {
        "author" => serde_json::from_str(include_str!(
            "../../../../schemas/v1/cli-task-input-author.schema.json"
        ))
        .map_err(|_| Failure::precondition("the embedded author schema is invalid")),
        "install" => install::schema(),
        _ => Err(Failure::input("this native task intent is unavailable")),
    }
}

fn current(row: &Row, owner: &runtime::Owner) -> Result<()> {
    if row.payload.identity != **owner {
        return Err(Failure::precondition(
            "the task belongs to a different registry owner or device",
        ));
    }
    Ok(())
}

/// Settled receipts remain readable after owner attachment, without granting
/// the original owner authority to execute another child operation.
fn history(row: &Row, owner: &runtime::Owner) -> Result<Value> {
    if !row.settled() || row.payload.identity != **owner && !owner.historical(&row.payload.identity)
    {
        return Err(Failure::precondition(
            "the task is not retained owner history",
        ));
    }
    row.view()
}

fn original(row: &Row, expected: &str) -> Result<()> {
    if row.original != expected {
        return Err(Failure::new(
            ErrorKind::Conflict,
            "the idempotency key names a different original task request",
        ));
    }
    Ok(())
}

fn revision(row: &Row, expected: i64) -> Result<()> {
    if expected != row.revision {
        return Err(Failure::new(
            ErrorKind::Conflict,
            "the task revision changed; read its current status",
        )
        .with_details([
            ("task_id".into(), row.id.clone().into()),
            ("revision".into(), row.revision.into()),
        ]));
    }
    Ok(())
}

fn save(store: &mut Store, row: &mut Row, state: &str) -> Result<()> {
    let previous = row.revision;
    row.advance(state, &moment())?;
    store.transaction(|t| journal::save(t, row, Some(previous)))
}

fn drain(store: &mut Store, row: Row) -> Result<Value> {
    let id = row.id.clone();
    drain_inner(store, row).map_err(|failure| {
        let mut details = vec![("task_id".into(), id.clone().into())];
        if let Ok(current) = journal::load(&store.connection, &id) {
            details.extend([
                ("revision".into(), current.revision.into()),
                ("task_state".into(), current.state.clone().into()),
                ("child_operation_ids".into(), json!(current.children())),
            ]);
        }
        failure.with_details(details)
    })
}

fn drain_inner(store: &mut Store, mut row: Row) -> Result<Value> {
    if row.settled() {
        return row.view();
    }
    if row.payload.input.question()?.is_some() {
        if row.state != "blocked" {
            save(store, &mut row, "blocked")?;
        }
        return row.view();
    }
    if row.payload.plan.is_none() {
        let plan = embedded::plan(
            store,
            row.payload.input.request()?,
            row.payload.identity.clone(),
            &moment(),
        )?;
        row.payload.plan_digest = Some(plan.digest()?);
        row.payload.plan = Some(service::Plan::Author(plan));
        save(store, &mut row, "running")?;
    }
    let plan = row
        .payload
        .plan
        .as_ref()
        .ok_or_else(|| Failure::precondition("the task child plan is absent"))?
        .author()?;
    let expected = row
        .payload
        .plan_digest
        .as_deref()
        .ok_or_else(|| Failure::precondition("the task child digest is absent"))?;
    let outcome = embedded::apply(store, plan, expected, &row.payload.identity, &moment())
        .map_err(|error| {
            error.with_details([
                ("task_id".into(), row.id.clone().into()),
                ("revision".into(), row.revision.into()),
                (
                    "child_operation_id".into(),
                    plan.operation_id.clone().into(),
                ),
            ])
        })?;
    row.outcome = Some(outcome);
    save(store, &mut row, "completed")?;
    row.view()
}

pub fn start(parent: &Path, intent: &str, key: &str, value: Value) -> Result<Value> {
    valid_key(key)?;
    let input = service::Input::stored(intent, value)?;
    let request = journal::encode(&input.value()?)?;
    let owner = runtime::owner(parent)?;
    {
        let store = owner.planning()?;
        if let Some(row) = journal::key(&store.connection, key)? {
            if row.payload.input.intent() != intent {
                return Err(Failure::input(
                    "the idempotency key belongs to another task intent",
                ));
            }
            original(&row, &request)?;
            if row.settled() {
                return history(&row, &owner);
            }
        }
    }
    input.admit()?;
    let claim = claim::Claim::open(parent, &owner, key)?;
    let mut store = owner.open(true)?;
    if let Some(row) = journal::key(&store.connection, key)? {
        if row.payload.input.intent() != intent {
            return Err(Failure::input(
                "the idempotency key belongs to another task intent",
            ));
        }
        original(&row, &request)?;
        if row.settled() {
            return history(&row, &owner);
        }
        current(&row, &owner)?;
        drop(store);
        return execute(parent, &owner, &claim, row, false);
    }
    let row = Row::new(input, (*owner).clone(), key, &moment())?;
    store.transaction(|t| journal::save(t, &row, None))?;
    drop(store);
    execute(parent, &owner, &claim, row, false)
}

fn execute(
    parent: &Path,
    owner: &runtime::Owner,
    claim: &claim::Claim,
    row: Row,
    cancel: bool,
) -> Result<Value> {
    claim.output()?;
    if matches!(row.payload.input, service::Input::Install(_)) {
        let id = row.id.clone();
        install::drain(parent, claim.output()?, owner, row, cancel).map_err(|failure| {
            let mut details = vec![("task_id".into(), id.clone().into())];
            if let Ok(store) = owner.planning()
                && let Ok(current) = journal::load(&store.connection, &id)
            {
                details.extend([
                    ("revision".into(), current.revision.into()),
                    ("task_state".into(), current.state.clone().into()),
                    ("child_operation_ids".into(), json!(current.children())),
                ]);
            }
            failure.with_details(details)
        })
    } else {
        drain(&mut owner.open(false)?, row)
    }
}

fn selected(store: &Store, id: Option<&str>) -> Result<Row> {
    if let Some(id) = id {
        return journal::load(&store.connection, id);
    }
    let mut rows = journal::unsettled(&store.connection)?;
    if rows.len() != 1 {
        return Err(Failure::new(
            ErrorKind::Conflict,
            "name the exact task; there is not exactly one unsettled task",
        ));
    }
    rows.pop()
        .ok_or_else(|| Failure::precondition("the task is absent"))
}

pub fn status(parent: &Path, id: Option<&str>) -> Result<Value> {
    let owner = runtime::owner(parent)?;
    let store = owner.planning()?;
    selected(&store, id)?.view()
}

pub fn list(parent: &Path) -> Result<Value> {
    let owner = runtime::owner(parent)?;
    let store = owner.planning()?;
    let rows = journal::unsettled(&store.connection)?;
    let tasks=rows.iter().map(|row| Ok(json!({"task_id":row.id,"revision":row.revision,"intent":row.payload.input.intent(),"state":row.state,
        "harness_id":row.payload.input.harness(),"project_root":row.payload.input.project(),"scope":row.payload.input.scope(),
        "open_question_ids":row.questions()?.iter().map(|q|q["question_id"].clone()).collect::<Vec<_>>(),"updated_at":row.updated})))
        .collect::<Result<Vec<_>>>()?;
    Ok(json!({"schema_version":1,"tasks":tasks}))
}

pub fn advance(
    parent: &Path,
    id: Option<&str>,
    expected: i64,
    answer: Option<(&str, &str)>,
    cancel: bool,
) -> Result<Value> {
    let owner = runtime::owner(parent)?;
    let (selected_id, key) = {
        let store = owner.planning()?;
        let row = selected(&store, id)?;
        revision(&row, expected)?;
        if row.settled() {
            if answer.is_some() {
                return Err(Failure::input("the task no longer accepts answers"));
            }
            return history(&row, &owner);
        }
        (row.id, row.key)
    };
    let claim = claim::Claim::open(parent, &owner, &key)?;
    let mut store = owner.open(false)?;
    let mut row = journal::load(&store.connection, &selected_id)?;
    revision(&row, expected)?;
    current(&row, &owner)?;
    if matches!(row.payload.input, service::Input::Install(_)) {
        if answer.is_some() {
            return Err(Failure::input(
                "the exact install task has no pending question",
            ));
        }
        drop(store);
        return execute(parent, &owner, &claim, row, cancel);
    }
    if cancel {
        if row.settled() {
            return row.view();
        }
        if let Some(plan) = &row.payload.plan {
            let plan = plan.author()?;
            match crate::store::journal::state(
                &store.connection,
                &plan.operation_id,
                &plan.action,
                &plan.digest()?,
            )?
            .as_deref()
            {
                // Cancellation cannot pretend committed immutable objects were
                // not written when the child outlived its task receipt.
                Some("verified") => return drain(&mut store, row),
                None => (),
                Some(_) => {
                    return Err(Failure::precondition(
                        "the author child is not a verified atomic operation",
                    ));
                }
            }
        }
        save(&mut store, &mut row, "cancelled")?;
        return row.view();
    }
    if let Some((question, value)) = answer {
        if row.settled() || row.payload.plan.is_some() {
            return Err(Failure::input("the task no longer accepts answers"));
        }
        row.payload.input = row.payload.input.answer(question, value)?;
        save(&mut store, &mut row, "planned")?;
    }
    drain(&mut store, row)
}

/// argv excludes the executable and retains the selected isolated state root.
pub(crate) fn continuations(parent: &Path, data: &Value) -> Vec<Value> {
    let (command, kind, actor, question) = match data["state"].as_str() {
        Some("planned" | "running") => ("continue", "advance", "cli", None),
        Some("blocked") if data.get("handoff").is_some() => ("continue", "blocked", "cli", None),
        Some("blocked") => (
            "answer",
            "blocked",
            "human",
            data["questions"][0]["question_id"].as_str(),
        ),
        _ => return Vec::new(),
    };
    let Some(id) = data["task_id"].as_str() else {
        return Vec::new();
    };
    let Some(revision) = data["revision"].as_i64() else {
        return Vec::new();
    };
    let Some(parent) = parent.to_str() else {
        return Vec::new();
    };
    let mut args = json!({"state-dir":parent,"task":id,"revision":revision});
    let mut argv = vec![
        "task".to_owned(),
        command.into(),
        "--state-dir".into(),
        parent.into(),
        "--task".into(),
        id.into(),
        "--revision".into(),
        revision.to_string(),
    ];
    let mut missing = Vec::new();
    if let Some(question) = question {
        args["question-id"] = question.into();
        argv.extend(["--question-id".into(), question.into()]);
        missing.push("value");
    }
    argv.push("--json".into());
    vec![
        json!({"kind":kind,"path":["task",command],"arguments":args,"argv":argv,"missing":missing,"actor":actor}),
    ]
}
