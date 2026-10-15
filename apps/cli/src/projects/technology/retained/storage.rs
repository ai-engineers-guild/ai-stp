//! Bounded retained rows and immutable receipts in the existing registry schema.

use std::collections::{BTreeMap, BTreeSet};

use rusqlite::{Connection, OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{ACTION, DETECTOR, MAX_BYTES, Plan, hash, invalid, sha256};
use crate::{error::Result, passport, store::database, wire};

const MAX_ROWS: usize = 8192;
// Leave room for the scan identity and outer machine response.
const MAX_ROW_BYTES: usize = MAX_BYTES - 64 * 1024;

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Evidence {
    source: String,
    path: String,
    digest: String,
    reference: String,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Claim {
    version: Option<String>,
    version_kind: String,
    evidence: Vec<Evidence>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Finding {
    kind: String,
    coordinate: String,
    context: String,
    technology_id: Option<String>,
    claims: Vec<Claim>,
}

#[derive(Clone, Serialize)]
pub(super) struct Row {
    #[serde(flatten)]
    finding: Finding,
    review: String,
    freshness: String,
    override_technology_id: Option<String>,
    override_version: Option<String>,
    first_seen_scan: String,
    last_seen_scan: String,
    reviewed_at: Option<String>,
    updated_at: String,
}

impl Finding {
    fn key(&self) -> (String, String, String) {
        (
            self.kind.clone(),
            self.coordinate.clone(),
            self.context.clone(),
        )
    }

    fn validate(&self) -> Result<()> {
        if !matches!(
            self.kind.as_str(),
            "package" | "configuration" | "alias" | "image"
        ) || !super::super::coordinate(&self.coordinate)
            || !matches!(
                self.context.as_str(),
                "production" | "development" | "testing" | "unspecified"
            )
            || self
                .technology_id
                .as_ref()
                .is_some_and(|v| !passport::stable_id(v, "technology"))
            || self.claims.is_empty()
            || self.claims.len() > super::super::LIMIT
        {
            return Err(invalid());
        }
        for claim in &self.claims {
            if !matches!(
                claim.version_kind.as_str(),
                "unknown" | "declared_range" | "locked_version" | "recorded_version"
            ) || (claim.version_kind == "unknown") != claim.version.is_none()
                || claim
                    .version
                    .as_ref()
                    .is_some_and(|v| super::super::version(v).as_ref() != Some(v))
                || claim.evidence.is_empty()
                || claim.evidence.len() > super::super::TRACE_LIMIT
            {
                return Err(invalid());
            }
            for trace in &claim.evidence {
                if !matches!(
                    trace.source.as_str(),
                    "declared" | "lock_file" | "checksum_file" | "configuration" | "source_file"
                ) || !sha256(&trace.digest)
                    || trace.path.is_empty()
                    || trace.path.len() > 32 * 1024
                    || trace.path.split('/').any(|p| matches!(p, "" | "." | ".."))
                    || trace.reference.len() > 256
                    || (!trace.reference.is_empty() && !super::super::coordinate(&trace.reference))
                {
                    return Err(invalid());
                }
            }
        }
        Ok(())
    }
}

impl Row {
    fn validate(&self) -> Result<()> {
        self.finding.validate()?;
        if !matches!(
            self.review.as_str(),
            "proposed" | "confirmed" | "rejected" | "overridden" | "retired"
        ) || !matches!(self.freshness.as_str(), "current" | "stale" | "absent")
            || !passport::stable_id(&self.first_seen_scan, "scan")
            || !passport::stable_id(&self.last_seen_scan, "scan")
            || !passport::timestamp(&self.updated_at)
            || self
                .reviewed_at
                .as_ref()
                .is_some_and(|v| !passport::timestamp(v))
            || self
                .override_technology_id
                .as_ref()
                .is_some_and(|v| !passport::stable_id(v, "technology"))
            || self
                .override_version
                .as_ref()
                .is_some_and(|v| super::super::version(v).as_ref() != Some(v))
        {
            return Err(invalid());
        }
        Ok(())
    }
}

pub(super) fn read(connection: &Connection, project: &str) -> Result<Vec<Row>> {
    let mut query = connection
        .prepare(
            "SELECT kind,coordinate,context,CASE WHEN length(claims)<=16777216 THEN claims END,
         technology_id,review,freshness,override_technology_id,override_version,
         first_seen_scan,last_seen_scan,reviewed_at,updated_at
         FROM tech_finding WHERE project_id=? AND scope='repository'
         ORDER BY kind,coordinate,context LIMIT 8193",
        )
        .map_err(database)?;
    let mut cursor = query.query([project]).map_err(database)?;
    let mut rows = Vec::new();
    let mut bytes = 0;
    let mut scans = BTreeSet::new();
    while let Some(row) = cursor.next().map_err(database)? {
        let claims: String = row.get(3).map_err(database)?;
        let finding = Finding {
            kind: row.get(0).map_err(database)?,
            coordinate: row.get(1).map_err(database)?,
            context: row.get(2).map_err(database)?,
            technology_id: row.get(4).map_err(database)?,
            claims: serde_json::from_value(wire::parse(claims.as_bytes())?)
                .map_err(|_| invalid())?,
        };
        let record = Row {
            finding,
            review: row.get(5).map_err(database)?,
            freshness: row.get(6).map_err(database)?,
            override_technology_id: row.get(7).map_err(database)?,
            override_version: row.get(8).map_err(database)?,
            first_seen_scan: row.get(9).map_err(database)?,
            last_seen_scan: row.get(10).map_err(database)?,
            reviewed_at: row.get(11).map_err(database)?,
            updated_at: row.get(12).map_err(database)?,
        };
        record.validate()?;
        bytes += serde_json::to_vec(&record).map_err(|_| invalid())?.len() + 1;
        if bytes + 2 > MAX_ROW_BYTES || rows.len() >= MAX_ROWS {
            return Err(invalid());
        }
        scans.insert(record.first_seen_scan.clone());
        scans.insert(record.last_seen_scan.clone());
        rows.push(record);
    }
    for scan in scans {
        let supported: bool = connection.query_row(
            "SELECT EXISTS(SELECT 1 FROM tech_scan WHERE scan_id=? AND project_id=? AND scope='repository' AND detector_version=?)",
            params![scan, project, DETECTOR], |r| r.get(0),
        ).map_err(database)?;
        if !supported {
            return Err(invalid());
        }
    }
    hash(&rows)?;
    Ok(rows)
}

pub(super) fn merge(
    prior: Vec<Row>,
    observation: &Value,
    scan: &str,
    at: &str,
) -> Result<Vec<Row>> {
    let complete = match observation["state"].as_str() {
        Some("complete") => true,
        Some("partial") => false,
        _ => return Err(invalid()),
    };
    let observed: Vec<Finding> =
        serde_json::from_value(observation["findings"].clone()).map_err(|_| invalid())?;
    let mut rows: BTreeMap<_, _> = prior
        .into_iter()
        .map(|mut row| {
            if complete {
                row.freshness = "absent".into();
            } else if row.freshness == "current" {
                row.freshness = "stale".into();
            }
            row.updated_at = at.into();
            (row.finding.key(), row)
        })
        .collect();
    for finding in observed {
        finding.validate()?;
        match rows.get_mut(&finding.key()) {
            Some(row) => {
                row.finding = finding;
                row.freshness = "current".into();
                row.last_seen_scan = scan.into();
            }
            None => {
                rows.insert(
                    finding.key(),
                    Row {
                        finding,
                        review: "proposed".into(),
                        freshness: "current".into(),
                        override_technology_id: None,
                        override_version: None,
                        reviewed_at: None,
                        first_seen_scan: scan.into(),
                        last_seen_scan: scan.into(),
                        updated_at: at.into(),
                    },
                );
            }
        }
    }
    if rows.len() > MAX_ROWS {
        return Err(invalid());
    }
    let rows: Vec<_> = rows.into_values().collect();
    if serde_json::to_vec(&rows).map_err(|_| invalid())?.len() > MAX_ROW_BYTES {
        return Err(invalid());
    }
    hash(&rows)?;
    Ok(rows)
}

pub(super) fn state_digest(connection: &Connection, project: &str, rows: &[Row]) -> Result<String> {
    // An empty observation still advances the scan history. Findings alone
    // would let competing empty plans both satisfy the same precondition.
    let latest: Option<(String, String)> = connection.query_row(
        "SELECT scan_id,detector_version FROM tech_scan WHERE project_id=? AND scope='repository' ORDER BY rowid DESC LIMIT 1",
        [project], |r| Ok((r.get(0)?, r.get(1)?)),
    ).optional().map_err(database)?;
    if latest
        .as_ref()
        .is_some_and(|(id, detector)| !passport::stable_id(id, "scan") || detector != DETECTOR)
    {
        return Err(invalid());
    }
    hash(&json!({"findings":rows,"latest_scan":latest}))
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Receipt {
    plan_digest: String,
    observation: Value,
}

pub(super) fn replay(connection: &Connection, plan: &Plan, digest: &str) -> Result<Option<Value>> {
    let record: Option<(String, String, String)> = connection.query_row(
        "SELECT kind,state,CASE WHEN length(detail)<=16777216 THEN detail END FROM operation WHERE operation_id=?",
        [&plan.operation_id], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
    ).optional().map_err(database)?;
    let Some((kind, state, detail)) = record else {
        return Ok(None);
    };
    let receipt: Receipt =
        serde_json::from_value(wire::parse(detail.as_bytes())?).map_err(|_| invalid())?;
    if kind != ACTION
        || state != "completed"
        || receipt.plan_digest != digest
        || hash(&receipt.observation)? != plan.observation_digest
    {
        return Err(invalid());
    }
    let observation = receipt.observation;
    let present: bool = connection
        .query_row(
            "SELECT EXISTS(SELECT 1 FROM tech_scan WHERE scan_id=? AND project_id=? AND scope=?
         AND complete=? AND stopped_by=? AND detector_version=? AND mapping_version=?
         AND created_at=? AND source_revision=?)",
            params![
                plan.scan_id(),
                plan.project_id,
                plan.scope,
                observation["state"] == "complete",
                observation["stopped_by"].as_str().unwrap_or(""),
                DETECTOR,
                observation["mapping"]["version"]
                    .as_str()
                    .ok_or_else(invalid)?,
                plan.created_at,
                plan.expected_revision
            ],
            |r| r.get(0),
        )
        .map_err(database)?;
    if !present {
        return Err(invalid());
    }
    Ok(Some(
        json!({"schema_version":1,"scan_id":plan.scan_id(),"project_id":plan.project_id,
        "scope":plan.scope,"created_at":plan.created_at,"observation":observation}),
    ))
}

pub(super) fn write(
    transaction: &Transaction<'_>,
    plan: &Plan,
    digest: &str,
    observation: &Value,
    rows: &[Row],
    at: &str,
) -> Result<()> {
    let detail = serde_json::to_string(&Receipt {
        plan_digest: digest.into(),
        observation: observation.clone(),
    })
    .map_err(|_| invalid())?;
    if detail.len() > MAX_BYTES {
        return Err(invalid());
    }
    transaction.execute(
        "INSERT INTO tech_scan(scan_id,project_id,scope,complete,stopped_by,detector_version,mapping_version,created_at,source_revision)
         VALUES(?,?,?,?,?,?,?,?,?)",
        params![plan.scan_id(), plan.project_id, plan.scope, observation["state"] == "complete",
            observation["stopped_by"].as_str().unwrap_or(""), DETECTOR,
            observation["mapping"]["version"].as_str().ok_or_else(invalid)?, plan.created_at, plan.expected_revision],
    ).map_err(database)?;
    let mut statement = transaction.prepare(
        "INSERT INTO tech_finding(project_id,scope,kind,coordinate,context,claims,technology_id,review,freshness,
         override_technology_id,override_version,first_seen_scan,last_seen_scan,reviewed_at,updated_at)
         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id,scope,kind,coordinate,context) DO UPDATE SET
         claims=excluded.claims,technology_id=excluded.technology_id,freshness=excluded.freshness,
         last_seen_scan=excluded.last_seen_scan,updated_at=excluded.updated_at",
    ).map_err(database)?;
    for row in rows {
        statement
            .execute(params![
                plan.project_id,
                plan.scope,
                row.finding.kind,
                row.finding.coordinate,
                row.finding.context,
                serde_json::to_string(&row.finding.claims).map_err(|_| invalid())?,
                row.finding.technology_id,
                row.review,
                row.freshness,
                row.override_technology_id,
                row.override_version,
                row.first_seen_scan,
                row.last_seen_scan,
                row.reviewed_at,
                row.updated_at
            ])
            .map_err(database)?;
    }
    transaction.execute(
        "INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES(?,?,'completed',?,?,?)",
        params![plan.operation_id, ACTION, at, at, detail],
    ).map_err(database)?;
    Ok(())
}
