//! Exact attribution from serialized verified mutations; plans are not observations.

use std::collections::{BTreeMap, BTreeSet};

use rusqlite::{Connection, OptionalExtension};

use crate::{
    error::{Failure, Result},
    store::database,
};

pub(super) const MAX_ROWS: usize = 100_000;

pub(crate) struct Installed {
    pub target: String,
    pub root: String,
    pub setup_id: String,
    pub version: String,
    pub native: bool,
    #[cfg(target_os = "linux")]
    pub native_roots: Vec<(String, crate::provider::configuration::plan::Identity)>,
}

pub(super) fn installed(connection: &Connection) -> Result<Vec<Installed>> {
    installed_except(connection, None)
}

fn installed_except(connection: &Connection, excluded: Option<&str>) -> Result<Vec<Installed>> {
    let members = aggregate_members(connection)?;
    let parent = excluded.and_then(|id| members.get(id));
    let mut operations = BTreeSet::new();
    let mut query = connection.prepare(
        "SELECT target,root,action,setup,version,detail,state,operation_id FROM ( \
         SELECT p.target_id AS target,coalesce(p.provider_target,'') AS root,p.action AS action, \
         coalesce(p.setup_stable_id,'') AS setup,coalesce(p.setup_version,'') AS version, \
         NULL AS detail,o.state AS state,o.operation_id AS operation_id,e.global_sequence AS ordering \
         FROM operation_plan p JOIN operation o ON o.operation_id=p.operation_id \
         JOIN operation_event e ON e.operation_id=p.operation_id AND e.state_after='verified' \
         WHERE o.state='verified' AND p.action IN ('install','update','remove','rollback') \
         UNION ALL \
         SELECT '', '', o.kind, '', '', \
         CASE WHEN length(CAST(o.detail AS BLOB))<=?1 THEN o.detail ELSE NULL END, \
         o.state,o.operation_id,e.global_sequence FROM operation o JOIN operation_event e ON e.operation_id=o.operation_id AND e.state_after=o.state \
         WHERE o.kind IN ('configuration.install','configuration.replace','configuration.remove','configuration.set') AND o.state IN ('applying','verified') \
         ) ORDER BY ordering DESC LIMIT ?2"
    ).map_err(database)?;
    let mut seen = BTreeSet::new();
    let mut pairs = BTreeSet::new();
    let mut unnamed = BTreeSet::new();
    let mut found = Vec::new();
    let rows = query
        .query_map(
            [
                crate::provider::configuration::set::RECORD_LIMIT as i64,
                (MAX_ROWS + 1) as i64,
            ],
            |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, String>(4)?,
                    row.get::<_, Option<String>>(5)?,
                    row.get::<_, String>(6)?,
                    row.get::<_, String>(7)?,
                ))
            },
        )
        .map_err(database)?;
    let mut read_bytes = 0usize;
    for (index, row) in rows.enumerate() {
        if index == MAX_ROWS {
            return Err(Failure::precondition(
                "the report exceeds 100000 retained configuration mutations",
            ));
        }
        let (
            mut target,
            mut root,
            mut action,
            mut setup_id,
            mut version,
            detail,
            state,
            operation_id,
        ) = row.map_err(database)?;
        if !operations.insert(operation_id.clone())
            || members.contains_key(&operation_id)
            || excluded == Some(operation_id.as_str())
            || parent == Some(&operation_id)
        {
            continue;
        }
        let mut group_roots = Vec::new();
        #[cfg(target_os = "linux")]
        let mut native_roots = Vec::new();
        let native = action.starts_with("configuration.");
        let harness = if native {
            let detail = detail.ok_or_else(super::invalid)?;
            read_bytes = read_bytes.saturating_add(detail.len());
            if read_bytes > 128 * 1024 * 1024 {
                return Err(Failure::precondition(
                    "the configuration history exceeds 128 MiB",
                ));
            }
            if action == crate::provider::configuration::set::KIND {
                let (_, plan) =
                    crate::provider::configuration::set::Record::parse(&detail, &state)?;
                if plan.operation_id != operation_id {
                    return Err(super::invalid());
                }
                let first = plan.first()?;
                root = plan
                    .project
                    .as_ref()
                    .map_or(first.target_path.clone(), |p| p.root.clone());
                target = format!(
                    "{}:{}",
                    plan.project
                        .as_ref()
                        .map_or(root.as_str(), |p| p.binding.project_id.as_str()),
                    first.harness_id
                );
                action = if state == "verified" && first.operation()? != "remove" {
                    "install"
                } else {
                    "remove"
                }
                .into();
                setup_id = first.setup["stable_id"].as_str().unwrap_or("").into();
                version = first.setup["version"].as_str().unwrap_or("").into();
                for child in &plan.children {
                    let child = child.parsed()?;
                    group_roots.push(child.target_path.clone());
                    #[cfg(target_os = "linux")]
                    native_roots.push((child.target_path, child.target_identity));
                }
                first.harness_id
            } else {
                let (_, plan) = crate::provider::configuration::record::Record::parse(
                    &detail, &action, &state,
                )?;
                if plan.operation_id != operation_id {
                    return Err(super::invalid());
                }
                root.clone_from(&plan.target_path);
                #[cfg(target_os = "linux")]
                native_roots.push((plan.target_path.clone(), plan.target_identity.clone()));
                target = format!(
                    "{}:{}",
                    plan.project
                        .as_ref()
                        .map_or(plan.target_path.as_str(), |binding| binding
                            .project_id
                            .as_str()),
                    plan.harness_id
                );
                action = if state == "verified" && plan.operation()? != "remove" {
                    "install"
                } else {
                    "remove"
                }
                .into();
                setup_id = plan.setup["stable_id"].as_str().unwrap_or("").into();
                version = plan.setup["version"].as_str().unwrap_or("").into();
                plan.harness_id
            }
        } else {
            target
                .split_once(':')
                .map_or("", |(_, harness)| harness)
                .to_owned()
        };
        let key = (
            harness.to_owned(),
            root.clone(),
            if root.is_empty() {
                target.clone()
            } else {
                String::new()
            },
        );
        let superseded = group_roots
            .iter()
            .any(|root| seen.contains(&(harness.clone(), root.clone(), String::new())))
            || seen.contains(&key)
            || unnamed.contains(&target)
            || (root.is_empty() && pairs.contains(&target));
        for root in group_roots {
            seen.insert((harness.clone(), root, String::new()));
        }
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
                root,
                setup_id,
                version,
                native,
                #[cfg(target_os = "linux")]
                native_roots,
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
    let root: Option<String> = connection
        .query_row(
            "SELECT root FROM project_root WHERE stable_id=?",
            [project],
            |row| row.get(0),
        )
        .optional()
        .map_err(database)?;
    let installed: BTreeSet<_> = installed(connection)?
        .into_iter()
        .filter(|item| {
            item.target == target
                && (!item.native || root.as_ref().is_some_and(|root| root == &item.root))
        })
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

/// Child receipts describe scope subsets. Only their parent can attest a complete setup.
fn aggregate_members(connection: &Connection) -> Result<BTreeMap<String, String>> {
    let mut query = connection.prepare("SELECT state,CASE WHEN length(CAST(detail AS BLOB))<=?1 THEN detail ELSE NULL END FROM operation WHERE kind='configuration.set' LIMIT ?2").map_err(database)?;
    let mut rows = query
        .query([
            crate::provider::configuration::set::RECORD_LIMIT as i64,
            (MAX_ROWS + 1) as i64,
        ])
        .map_err(database)?;
    let mut members = BTreeMap::new();
    let mut count = 0;
    let mut bytes = 0usize;
    while let Some(row) = rows.next().map_err(database)? {
        count += 1;
        let state: String = row.get(0).map_err(database)?;
        let detail: Option<String> = row.get(1).map_err(database)?;
        let detail = detail.ok_or_else(super::invalid)?;
        bytes = bytes.saturating_add(detail.len());
        if count > MAX_ROWS || bytes > 128 * 1024 * 1024 {
            return Err(super::invalid());
        }
        let (_, plan) = crate::provider::configuration::set::Record::parse(&detail, &state)?;
        for child in &plan.children {
            if members
                .insert(child.parsed()?.operation_id, plan.operation_id.clone())
                .is_some()
            {
                return Err(super::invalid());
            }
        }
    }
    Ok(members)
}

/// Current installation relationships before one native operation or its parent.
#[cfg(target_os = "linux")]
pub(crate) fn installed_before(connection: &Connection, operation: &str) -> Result<Vec<Installed>> {
    installed_except(connection, Some(operation))
}
