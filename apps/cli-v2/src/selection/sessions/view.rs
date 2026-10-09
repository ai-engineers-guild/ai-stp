//! Bounded session discovery from one registry transaction, without credentials.

use rusqlite::{OptionalExtension, params};
use serde_json::{Value, json};

use super::{invalid, records::require};
use crate::{
    canonical, digest,
    error::{Failure, Result},
    harnesses,
    objects::Objects,
    passport,
    store::{Store, database},
};

const MAX_PAGE: usize = 4 * 1024 * 1024;

/// A cursor orders proposal identities, not offsets that shift after decisions.
/// Each page is a fresh observation; it is never an eligibility or install permit.
pub fn read(
    store: &mut Store,
    project: &str,
    harness: &str,
    after: Option<&str>,
    limit: usize,
    at: &str,
) -> Result<Value> {
    if !passport::stable_id(project, "project")
        || harness == "undefined"
        || !passport::timestamp(at)
        || !(1..=100).contains(&limit)
        || after.is_some_and(|id| !passport::stable_id(id, "proposal"))
    {
        return Err(Failure::input(
            "name a project, harness, valid cursor and a page limit from 1 to 100",
        ));
    }
    harnesses::definition(harness)?;
    store.transaction(|t| {
        let objects = Objects { connection: t };
        objects.require_active(project)?;
        objects.head("project", project)?;
        let mut statement = t.prepare(
            "SELECT proposal_id,length(CAST(graph AS BLOB)) FROM proposal WHERE project_id=? AND harness_id=? AND cancelled_at IS NULL AND confirmed_stable_id IS NULL AND expires_at>? AND proposal_id>? ORDER BY proposal_id LIMIT ?",
        ).map_err(database)?;
        let rows = statement.query_map(params![project,harness,at,after.unwrap_or(""),limit as i64 + 1],
            |row|Ok((row.get::<_,String>(0)?,row.get::<_,i64>(1)?)))
            .map_err(database)?.collect::<std::result::Result<Vec<_>,_>>().map_err(database)?;
        let mut proposals = Vec::new();
        let mut bytes = 0usize;
        for (id, size) in rows.iter().take(limit) {
            let size = usize::try_from(*size).map_err(|_| invalid())?;
            if size > super::MAX_BYTES || bytes.saturating_add(size) > MAX_PAGE {
                return Err(Failure::precondition("the session page exceeds its byte bound; reduce limit"));
            }
            let proposal = require(t, id)?;
            if proposal.project_id != project || proposal.harness_id != harness || proposal.state(at)? != "open" {
                return Err(invalid());
            }
            let mut item = serde_json::to_value(&proposal).map_err(|_| invalid())?;
            item["state"] = "open".into();
            bytes = bytes.saturating_add(canonical::bytes(&item)?.len());
            if bytes > MAX_PAGE {
                return Err(Failure::precondition("the session page exceeds its byte bound; reduce limit"));
            }
            proposals.push(item);
        }
        let held = t.query_row(
            "SELECT stable_id,version,state,selected_at FROM selected_version WHERE project_id=? AND harness_id=?",
            params![project,harness],|r|Ok((r.get::<_,String>(0)?,r.get::<_,String>(1)?,r.get::<_,String>(2)?,r.get::<_,String>(3)?)))
            .optional().map_err(database)?;
        let selected = if let Some((id, version, state, selected_at)) = held {
            if !passport::stable_id(&id, "setup") || !matches!(state.as_str(), "pending_install" | "installed") || !passport::timestamp(&selected_at) {
                return Err(invalid());
            }
            let document = objects.exact_version(&id, &version, None)?;
            if document["harness_id"] != harness {
                return Err(invalid());
            }
            json!({"stable_id":id,"version":version,"passport_digest":digest::canonical("ai-stp:passport:v1",&document)?,
                "recorded_state":state,"selected_at":selected_at})
        } else { Value::Null };
        Ok(json!({"schema_version":1,"project_id":project,"harness_id":harness,"observed_at":at,
            "proposals":proposals,"selected":selected,"next_after":if rows.len()>limit {rows.get(limit-1).map(|r|r.0.as_str())} else {None},
            "context_freshness":"not_evaluated","installation_observed":false}))
    })
}
