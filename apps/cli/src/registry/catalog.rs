//! Public catalog observation and explicit account-bound private acquisition.

use clap::ArgMatches;
use serde_json::Value;
use std::path::{Path, PathBuf};

use super::Handler;
use crate::{
    account::access::Access,
    authoring::runtime,
    catalog,
    error::{Failure, Result},
    http::Endpoint,
};

fn path<'a>(leaf: &'a ArgMatches, name: &str) -> Option<&'a Path> {
    leaf.try_get_one::<PathBuf>(name)
        .ok()
        .flatten()
        .map(PathBuf::as_path)
}

fn text<'a>(leaf: &'a ArgMatches, name: &str) -> Result<&'a str> {
    leaf.get_one::<String>(name)
        .map(String::as_str)
        .ok_or_else(|| Failure::input(format!("{name} is required")))
}

fn flag(leaf: &ArgMatches, name: &str) -> bool {
    leaf.try_get_one::<bool>(name)
        .ok()
        .flatten()
        .copied()
        .unwrap_or(false)
}

pub(super) fn plan(leaf: &ArgMatches) -> Result<Value> {
    let root =
        path(leaf, "state-dir").ok_or_else(|| Failure::input("state directory is required"))?;
    let config = path(leaf, "config");
    let mut access = if flag(leaf, "private") {
        let endpoint = Endpoint::configured(config)?;
        Some(Access::load(
            root,
            &endpoint.base.origin().ascii_serialization(),
            false,
        )?)
    } else {
        None
    };
    if let Some(access) = &mut access {
        access.verify()?;
    }
    runtime::plan(root, |_, identity, at| {
        catalog::acquisition::plan_with_access(
            config,
            text(leaf, "id")?,
            text(leaf, "version")?,
            identity,
            at,
            access.as_ref(),
        )
    })
}

pub(super) fn read(leaf: &ArgMatches, handler: Handler) -> Result<Value> {
    let config = path(leaf, "config");
    let cache = path(leaf, "cache-dir");
    let offline = flag(leaf, "offline");
    let kind = catalog::Kind::parse(text(leaf, "kind")?)?;
    let connection = leaf
        .try_get_one::<String>("connection")
        .ok()
        .flatten()
        .map(String::as_str);
    if connection.is_some() && !flag(leaf, "private") {
        return Err(Failure::input(
            "a retained catalog connection requires an explicit private read",
        ));
    }
    if matches!(handler, Handler::CatalogVersion) && flag(leaf, "private") {
        let root = path(leaf, "state-dir")
            .ok_or_else(|| Failure::input("private reads require an isolated state directory"))?;
        if connection.is_some() {
            return catalog::private::version_with_access(
                config,
                cache,
                kind,
                text(leaf, "id")?,
                text(leaf, "version")?,
                offline,
                Access::for_connection(root, None, connection, offline)?,
            );
        }
        return catalog::private::version(
            config,
            cache,
            root,
            kind,
            text(leaf, "id")?,
            text(leaf, "version")?,
            offline,
        );
    }
    let reader = catalog::Reader::new(config, cache, offline)?;
    if matches!(handler, Handler::CatalogSearch) {
        reader.search(
            kind,
            leaf.get_one::<String>("query").map(String::as_str),
            leaf.get_one::<String>("cursor").map(String::as_str),
            leaf.get_one::<String>("limit").map(String::as_str),
            flag(leaf, "include-experimental"),
        )
    } else {
        reader.show(
            kind,
            text(leaf, "id")?,
            leaf.try_get_one::<String>("version")
                .ok()
                .flatten()
                .map(String::as_str),
        )
    }
}
