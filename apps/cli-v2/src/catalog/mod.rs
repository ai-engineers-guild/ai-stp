//! Public catalog observation, with explicit offline provenance and no account access.

pub mod acquisition;
mod cache;
use crate::{
    digest,
    error::{ErrorKind, Failure, Result},
    http::{self, Endpoint},
    passport,
    wire::Schema,
};
use serde_json::{Value, json};
use std::{collections::BTreeSet, path::Path};

static COMPONENT_LIST: Schema = Schema::reader(include_str!(
    "../../../../schemas/v1/catalog-component-list.schema.json"
));
static SETUP_LIST: Schema = Schema::reader(include_str!(
    "../../../../schemas/v1/catalog-setup-list.schema.json"
));
static COMPONENT_DETAIL: Schema = Schema::reader(include_str!(
    "../../../../schemas/v1/catalog-component-detail.schema.json"
));
static SETUP_DETAIL: Schema = Schema::reader(include_str!(
    "../../../../schemas/v1/catalog-setup-detail.schema.json"
));
static COMPONENT_VERSION: Schema = Schema::reader(include_str!(
    "../../../../schemas/v1/catalog-component-version.schema.json"
));
static SETUP_VERSION: Schema = Schema::reader(include_str!(
    "../../../../schemas/v1/catalog-setup-version.schema.json"
));

#[derive(Clone, Copy)]
pub enum Kind {
    Component,
    Setup,
}
impl Kind {
    pub fn parse(text: &str) -> Result<Self> {
        match text {
            "component" => Ok(Self::Component),
            "setup" => Ok(Self::Setup),
            _ => Err(Failure::input("catalog kind must be component or setup")),
        }
    }
    pub fn name(self) -> &'static str {
        match self {
            Self::Component => "component",
            Self::Setup => "setup",
        }
    }
    fn route(self) -> &'static str {
        match self {
            Self::Component => "components",
            Self::Setup => "setups",
        }
    }
    fn schema(self, version: bool) -> &'static Schema {
        match (self, version) {
            (Self::Component, false) => &COMPONENT_DETAIL,
            (Self::Component, true) => &COMPONENT_VERSION,
            (Self::Setup, false) => &SETUP_DETAIL,
            (Self::Setup, true) => &SETUP_VERSION,
        }
    }
}

fn moment() -> String {
    format!("{:.3}", jiff::Timestamp::now())
}
fn invalid() -> Failure {
    Failure::precondition(
        "catalog response identity, publication or trust does not match the request",
    )
}
fn trust(value: &Value) -> Result<()> {
    if value["trust_lane"] == "authoritative"
        && (value["author_verified"] != true || value["component_verified"] != true)
    {
        return Err(invalid());
    }
    Ok(())
}

fn support(value: &Value) -> Result<()> {
    if value["state"] == "verified" {
        let evidence = value["evidence"].as_array().ok_or_else(invalid)?;
        let mandatory: Vec<_> = evidence
            .iter()
            .filter(|row| row["mandatory"] == true)
            .collect();
        if mandatory.is_empty() || mandatory.iter().any(|row| row["result"] != "passed") {
            return Err(invalid());
        }
    }
    Ok(())
}

pub struct Reader<'a> {
    endpoint: Endpoint,
    cache: Option<&'a Path>,
    offline: bool,
}
impl<'a> Reader<'a> {
    pub fn new(config: Option<&Path>, cache: Option<&'a Path>, offline: bool) -> Result<Self> {
        if offline && cache.is_none() {
            return Err(Failure::input(
                "offline catalog reads require an explicit cache directory",
            ));
        }
        Ok(Self {
            endpoint: Endpoint::configured(config)?,
            cache,
            offline,
        })
    }

    pub fn search(
        &self,
        kind: Kind,
        query: Option<&str>,
        cursor: Option<&str>,
        limit: Option<&str>,
        experimental: bool,
    ) -> Result<Value> {
        if self.offline {
            return Err(Failure::input(
                "catalog search requires a live page; only exact objects are cached",
            ));
        }
        let limit = limit
            .unwrap_or("20")
            .parse::<u32>()
            .map_err(|_| Failure::input("limit must be a whole number from 1 to 100"))?;
        if !(1..=100).contains(&limit)
            || query.is_some_and(|q| q.is_empty() || q.chars().count() > 200)
            || cursor.is_some_and(|c| {
                c.is_empty()
                    || c.len() > 512
                    || !c
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
            })
        {
            return Err(Failure::input(
                "catalog query, cursor or page size is outside its contract bounds",
            ));
        }
        let limit_text = limit.to_string();
        let mut parameters = vec![
            ("page_size", limit_text.as_str()),
            (
                "include_experimental",
                if experimental { "true" } else { "false" },
            ),
        ];
        if let Some(query) = query {
            parameters.push(("q", query));
        }
        if let Some(cursor) = cursor {
            parameters.push(("cursor", cursor));
        }
        let url = self.endpoint.route(&[kind.route()], &parameters)?;
        let document = self.endpoint.get(&url)?;
        match kind {
            Kind::Component => &COMPONENT_LIST,
            Kind::Setup => &SETUP_LIST,
        }
        .validate(&document)?;
        let mut ids = BTreeSet::new();
        for (field, lane) in [("items", "authoritative"), ("experimental", "experimental")] {
            for item in document[field].as_array().ok_or_else(invalid)? {
                trust(&item["latest_trust"])?;
                support(&item["latest_support"])?;
                let id = item["stable_id"].as_str().ok_or_else(invalid)?;
                if !passport::stable_id(id, kind.name())
                    || item["latest_trust"]["trust_lane"] != lane
                    || !ids.insert(id)
                    || (field == "experimental" && !experimental)
                {
                    return Err(invalid());
                }
            }
        }
        if ids.len() > limit as usize {
            return Err(invalid());
        }
        Ok(
            json!({"schema_version": 1, "kind": kind.name(), "source": "online", "checked_at": moment(),
            "items": document["items"], "experimental": document["experimental"], "next_cursor": document["page"]["next_cursor"]}),
        )
    }

    pub fn show(&self, kind: Kind, id: &str, version: Option<&str>) -> Result<Value> {
        if !passport::stable_id(id, kind.name())
            || version.is_some_and(|v| !passport::version_number(v))
        {
            return Err(Failure::input(
                "catalog reads require a matching stable identifier and exact X.Y version",
            ));
        }
        let mut segments = vec![kind.route(), id];
        if let Some(version) = version {
            segments.extend(["versions", version]);
        }
        let url = self.endpoint.route(&segments, &[])?;
        let remote = if self.offline {
            Err(http::unavailable())
        } else {
            self.endpoint.get(&url)
        };
        let (document, source, checked_at) = match remote {
            Ok(document) => {
                validate(kind, id, version, &document)?;
                let checked_at = moment();
                if let Some(root) = self.cache {
                    let cache = cache::Cache::open(root, true)?.ok_or_else(invalid)?;
                    cache.store(url.as_str(), &document, &checked_at)?;
                }
                (document, "online", checked_at)
            }
            Err(failure) if matches!(failure.kind, ErrorKind::Unavailable) => {
                let entry = self
                    .cache
                    .map(|root| cache::Cache::open(root, false))
                    .transpose()?
                    .flatten()
                    .map(|cache| cache.load(url.as_str()))
                    .transpose()?
                    .flatten()
                    .ok_or(failure)?;
                validate(kind, id, version, &entry.document)?;
                (entry.document, "cache", entry.checked_at)
            }
            Err(failure) => return Err(failure),
        };
        if version.is_some() {
            Ok(
                json!({"schema_version": 1, "distribution_visibility": "public", "kind": kind.name(),
                "source": source, "checked_at": checked_at, "passport_digest": document["passport_digest"],
                "lifecycle": document["lifecycle"], "trust": document["trust"], "published_at": document["published_at"], "passport": document["passport"]}),
            )
        } else {
            Ok(
                json!({"schema_version": 1, "kind": kind.name(), "source": source, "checked_at": checked_at,
                "summary": document["summary"], "versions": document["versions"]}),
            )
        }
    }
}

fn validate(kind: Kind, id: &str, version: Option<&str>, document: &Value) -> Result<()> {
    kind.schema(version.is_some()).validate(document)?;
    if document["visibility"] == "private" || document["distribution_visibility"] == "private" {
        return Err(invalid());
    }
    if let Some(version) = version {
        let passport = &document["passport"];
        passport::validate_identity(passport)?;
        passport::versions::validate(passport)?;
        if passport["stable_id"] != id
            || passport["kind"] != kind.name()
            || passport["version"] != version
            || (passport["visibility"] != "public"
                && document["distribution_visibility"] != "public")
            || digest::canonical("ai-stp:passport:v1", passport)? != document["passport_digest"]
        {
            return Err(invalid());
        }
        trust(&document["trust"])?;
        support(&document["support"])?;
    } else {
        if document["summary"]["stable_id"] != id {
            return Err(invalid());
        }
        trust(&document["summary"]["latest_trust"])?;
        support(&document["summary"]["latest_support"])?;
        for version in document["versions"].as_array().ok_or_else(invalid)? {
            trust(&version["trust"])?;
            support(&version["support"])?;
        }
    }
    Ok(())
}
