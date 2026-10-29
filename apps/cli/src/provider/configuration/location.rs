//! Location metadata must not retarget a retained provider-owned installation.

use std::path::Path;

use cap_std::fs::Dir;
use rusqlite::Connection;

use super::{invalid, record, set};
use crate::{
    error::{Failure, Result},
    files::physical,
    store::database,
};

fn available(
    target: &Path,
    target_identity: &[String; 2],
    state: &str,
    checkout: &Dir,
    previous: &Path,
    destination: &Path,
    identity: &[String; 2],
) -> Result<()> {
    if target_identity == identity
        || target.starts_with(previous)
        || target.starts_with(destination)
        || previous.starts_with(target)
        || destination.starts_with(target)
    {
        return Err(Failure::precondition(
            "review provider-owned target relocation through its context-owned task before moving this checkout",
        ));
    }
    match Dir::open_ambient_dir(target, cap_std::ambient_authority()) {
        Ok(held) => physical::require_disjoint(checkout, &held),
        Err(_) if state != "applying" => Ok(()),
        Err(_) => Err(Failure::precondition(
            "an unfinished provider target cannot be proved disjoint from this checkout",
        )),
    }
}

pub(crate) fn location_unreserved(
    connection: &Connection,
    previous: &Path,
    destination: &Path,
    identity: &[String; 2],
) -> Result<()> {
    // Production transfer already requires legacy work to settle. Preserve
    // that fence if an opaque old record is encountered later; never interpret
    // it as a native continuation or guess its physical ownership.
    for query in [
        "SELECT EXISTS(SELECT 1 FROM operation_plan p JOIN operation o USING(operation_id) WHERE o.finished_at IS NULL)",
        "SELECT EXISTS(SELECT 1 FROM installation_transaction WHERE state NOT IN ('verified','rolled_back','cancelled'))",
    ] {
        if connection
            .query_row(query, [], |row| row.get::<_, bool>(0))
            .map_err(database)?
        {
            return Err(Failure::precondition(
                "finish the retained legacy installation before reviewing a checkout location",
            ));
        }
    }
    let checkout =
        Dir::open_ambient_dir(destination, cap_std::ambient_authority()).map_err(|_| invalid())?;
    let mut query = connection.prepare(
        "SELECT kind,state,CASE WHEN length(CAST(detail AS BLOB))<=50331648 THEN detail ELSE NULL END FROM operation WHERE kind IN ('configuration.install','configuration.replace','configuration.remove','configuration.set') ORDER BY operation_id LIMIT 1001",
    ).map_err(database)?;
    let mut rows = query.query([]).map_err(database)?;
    let mut count = 0;
    while let Some(row) = rows.next().map_err(database)? {
        count += 1;
        if count > 1000 {
            return Err(Failure::precondition(
                "provider history exceeds the bounded location review",
            ));
        }
        let kind: String = row.get(0).map_err(database)?;
        let state: String = row.get(1).map_err(database)?;
        let detail: Option<String> = row.get(2).map_err(database)?;
        let detail = detail.ok_or_else(invalid)?;
        if kind == set::KIND {
            let (_, plan) = set::Record::parse(&detail, &state)?;
            if let Some(project) = &plan.project {
                available(
                    Path::new(&project.root),
                    &project.root_identity,
                    &state,
                    &checkout,
                    previous,
                    destination,
                    identity,
                )?;
            }
            for child in &plan.children {
                let child = child.parsed()?;
                available(
                    Path::new(&child.target_path),
                    &child.target_identity,
                    &state,
                    &checkout,
                    previous,
                    destination,
                    identity,
                )?;
            }
        } else {
            let (_, plan) = record::Record::parse(&detail, &kind, &state)?;
            available(
                Path::new(&plan.target_path),
                &plan.target_identity,
                &state,
                &checkout,
                previous,
                destination,
                identity,
            )?;
        }
    }
    Ok(())
}
