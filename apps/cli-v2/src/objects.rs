//! Verified local object evidence from an explicit immutable snapshot.

use rusqlite::OptionalExtension;
use serde_json::{Value, json};

use crate::{
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    passport,
    snapshot::Snapshot,
};

fn database(_: rusqlite::Error) -> Failure {
    Failure::precondition("snapshot object records are not readable")
}

fn absent() -> Failure {
    Failure::new(
        ErrorKind::NotFound,
        "the requested local passport does not exist",
    )
}

impl Snapshot {
    pub fn exact_version(&self, id: &str, version: &str, expected: Option<&str>) -> Result<Value> {
        if (!passport::stable_id(id, "component") && !passport::stable_id(id, "setup"))
            || !passport::version_number(version)
        {
            return Err(Failure::input(
                "an exact version requires a component or setup id and X.Y number",
            ));
        }
        let row: Option<(String, String, i64, i64)> = self.connection.query_row(
            "SELECT revision_id, passport_digest, major, minor FROM object_version WHERE stable_id = ? AND version = ?",
            [id, version], |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        ).optional().map_err(database)?;
        let (revision, held, major, minor) = row.ok_or_else(absent)?;
        let document = self.revision(&revision)?;
        if major < 0
            || minor < 0
            || version != format!("{major}.{minor}")
            || document["stable_id"] != id
            || document["version"] != version
            || digest::canonical("ai-stp:passport:v1", &document)? != held
            || expected.is_some_and(|expected| expected != held)
        {
            return Err(Failure::new(
                ErrorKind::Conflict,
                "an exact dependency disagrees with its recorded identity",
            ));
        }
        passport::versions::validate_document(&document)?;
        Ok(document)
    }

    pub fn passport(&self, kind: &str, id: Option<&str>) -> Result<Value> {
        let id = match id {
            Some(value) => value.to_owned(),
            None => {
                let mut statement = self
                    .connection
                    .prepare(
                        "SELECT stable_id FROM entity WHERE kind = ? ORDER BY created_at LIMIT 2",
                    )
                    .map_err(database)?;
                let ids = statement
                    .query_map([kind], |row| row.get::<_, String>(0))
                    .map_err(database)?
                    .collect::<std::result::Result<Vec<_>, _>>()
                    .map_err(database)?;
                if ids.len() > 1 {
                    return Err(Failure::new(
                        ErrorKind::Conflict,
                        "snapshot contains multiple passports of a singleton kind",
                    ));
                }
                ids.first().ok_or_else(absent)?.clone()
            }
        };
        if !passport::stable_id(&id, kind) {
            return Err(Failure::input(
                "passport identifier must match the requested kind",
            ));
        }
        let mut statement = self
            .connection
            .prepare("SELECT revision_id FROM head WHERE stable_id = ? LIMIT 2")
            .map_err(database)?;
        let heads = statement
            .query_map([&id], |row| row.get::<_, String>(0))
            .map_err(database)?
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(database)?;
        if heads.len() > 1 {
            return Err(Failure::new(
                ErrorKind::Conflict,
                "this object has multiple heads and requires a merge",
            ));
        }
        let document = self.revision(heads.first().ok_or_else(absent)?)?;
        if document["stable_id"] != id || document["kind"] != kind {
            return Err(Failure::precondition(
                "snapshot head points to another object",
            ));
        }
        Ok(passport::view(&document))
    }

    pub fn revision(&self, id: &str) -> Result<Value> {
        let row: Option<(String, String, String, String)> = self.connection.query_row(
            "SELECT r.content, r.stable_id, r.created_at, e.kind FROM revision r JOIN entity e ON e.stable_id = r.stable_id WHERE r.revision_id = ?",
            [id], |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        ).optional().map_err(database)?;
        let (content, stable_id, created_at, kind) = row.ok_or_else(absent)?;
        let document = canonical::parse(content.as_bytes())?;
        passport::validate(&document)?;
        if document["revision_id"] != id
            || document["stable_id"] != stable_id
            || document["created_at"] != created_at
            || document["kind"] != kind
        {
            return Err(Failure::precondition(
                "snapshot revision metadata disagrees with its passport",
            ));
        }
        let mut statement = self.connection.prepare("SELECT parent_revision_id FROM revision_parent WHERE revision_id = ? ORDER BY parent_revision_id").map_err(database)?;
        let parents = statement
            .query_map([id], |row| row.get::<_, String>(0))
            .map_err(database)?
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(database)?;
        let mut declared: Vec<_> = document["parent_revision_ids"]
            .as_array()
            .ok_or_else(|| Failure::precondition("passport parents are invalid"))?
            .iter()
            .filter_map(Value::as_str)
            .collect();
        declared.sort_unstable();
        if declared != parents {
            return Err(Failure::precondition(
                "snapshot parent links disagree with the passport",
            ));
        }
        Ok(document)
    }

    pub fn versions(&self, id: &str) -> Result<Value> {
        if !passport::stable_id(id, "component") && !passport::stable_id(id, "setup") {
            return Err(Failure::input(
                "version history requires a component or setup identifier",
            ));
        }
        let mut statement = self.connection.prepare("SELECT version, major, minor, passport_digest, revision_id, created_at FROM object_version WHERE stable_id = ? ORDER BY major, minor").map_err(database)?;
        let rows = statement
            .query_map([id], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, i64>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, String>(4)?,
                    row.get::<_, String>(5)?,
                ))
            })
            .map_err(database)?;
        let mut versions = Vec::new();
        let mut next = "1.0".to_owned();
        for row in rows {
            let (version, major, minor, expected, revision, created) = row.map_err(database)?;
            let document = self.revision(&revision)?;
            if major < 0
                || minor < 0
                || !passport::timestamp(&created)
                || version != format!("{major}.{minor}")
                || document["stable_id"] != id
                || document["version"] != version
                || digest::canonical("ai-stp:passport:v1", &document)? != expected
            {
                return Err(Failure::precondition(
                    "immutable version coordinates or digest disagree with its passport",
                ));
            }
            next = format!(
                "{major}.{}",
                minor
                    .checked_add(1)
                    .ok_or_else(|| Failure::precondition("version number overflow"))?
            );
            versions.push(json!({"schema_version": 1, "version": version, "passport_digest": expected, "revision_id": revision, "created_at": created}));
        }
        let fork: Option<(String, String)> = self
            .connection
            .query_row(
                "SELECT source_stable_id, source_version FROM fork_origin WHERE stable_id = ?",
                [id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()
            .map_err(database)?;
        Ok(
            json!({"schema_version": 1, "stable_id": id, "versions": versions, "next_minor": next,
            "forked_from": fork.as_ref().map(|f| &f.0), "forked_from_version": fork.as_ref().map(|f| &f.1),
            "publishable": null, "publish_reason": null}),
        )
    }
}
