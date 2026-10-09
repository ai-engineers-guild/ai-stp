//! Exact attribution from serialized verified mutations; plans are not observations.

use std::collections::BTreeSet;

use rusqlite::{Connection, OptionalExtension};

use crate::{error::Result, store::database};

pub(super) struct Installed {
    pub target: String,
    pub setup_id: String,
    pub version: String,
}

pub(super) fn installed(connection: &Connection) -> Result<Vec<Installed>> {
    let mut query = connection
        .prepare(
            "SELECT p.target_id, coalesce(p.provider_target,''), p.action, \
         coalesce(p.setup_stable_id,''), coalesce(p.setup_version,'') \
         FROM operation_plan p JOIN operation o ON o.operation_id=p.operation_id \
         JOIN operation_event e ON e.operation_id=p.operation_id AND e.state_after='verified' \
         WHERE o.state='verified' AND p.action IN ('install','update','remove','rollback') \
         ORDER BY e.global_sequence DESC",
        )
        .map_err(database)?;
    let mut seen = BTreeSet::new();
    let mut pairs = BTreeSet::new();
    let mut unnamed = BTreeSet::new();
    let mut found = Vec::new();
    let rows = query
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, String>(4)?,
            ))
        })
        .map_err(database)?;
    for row in rows {
        let (target, root, action, setup_id, version) = row.map_err(database)?;
        let harness = target.split_once(':').map_or("", |(_, harness)| harness);
        let key = (
            harness.to_owned(),
            root.clone(),
            if root.is_empty() {
                target.clone()
            } else {
                String::new()
            },
        );
        let superseded = seen.contains(&key)
            || unnamed.contains(&target)
            || (root.is_empty() && pairs.contains(&target));
        seen.insert(key);
        pairs.insert(target.clone());
        if root.is_empty() {
            unnamed.insert(target.clone());
        }
        if !superseded
            && matches!(action.as_str(), "install" | "update")
            && !setup_id.is_empty()
            && !version.is_empty()
        {
            found.push(Installed {
                target,
                setup_id,
                version,
            });
        }
    }
    Ok(found)
}

pub(super) fn baseline(
    connection: &Connection,
    project: &str,
    harness: &str,
) -> Result<Option<(String, String, &'static str)>> {
    let target = format!("{project}:{harness}");
    let installed: BTreeSet<_> = installed(connection)?
        .into_iter()
        .filter(|item| item.target == target)
        .map(|item| (item.setup_id, item.version))
        .collect();
    if installed.len() == 1 {
        return Ok(installed
            .into_iter()
            .next()
            .map(|(id, version)| (id, version, "installed")));
    }
    connection
        .query_row(
            "SELECT stable_id, version FROM selected_version WHERE project_id=? AND harness_id=?",
            [project, harness],
            |row| Ok((row.get(0)?, row.get(1)?, "selected")),
        )
        .optional()
        .map_err(database)
}
