//! Noninteractive Secret Service over the local Unix session bus.
//!
//! The standard `plain` session avoids custom cryptography. Bus transport must be
//! local; at-rest protection belongs to the user's existing credential service.
//! No Unlock, Prompt, CreateCollection, replacement or fallback is permitted.

use std::{collections::HashMap, time::Duration};
use zbus::{
    address::{Address, transport::Transport},
    blocking::{Connection, Proxy, connection::Builder, proxy},
    proxy::CacheProperties,
    zvariant::{OwnedObjectPath, OwnedValue, Value},
};
use zeroize::Zeroizing;

use super::credentials::unavailable;
use crate::error::Result;

const SERVICE: &str = "org.freedesktop.secrets";
type Secret = (OwnedObjectPath, Vec<u8>, Vec<u8>, String);

fn connection() -> Result<Connection> {
    let address = Address::session().map_err(|_| unavailable())?;
    if !matches!(address.transport(), Transport::Unix(_)) {
        return Err(unavailable());
    }
    Builder::address(address)
        .map_err(|_| unavailable())?
        .method_timeout(Duration::from_secs(3))
        .build()
        .map_err(|_| unavailable())
}

fn proxy<'a>(conn: &'a Connection, path: &'a str, interface: &'a str) -> Result<Proxy<'a>> {
    proxy::Builder::new(conn)
        .destination(SERVICE)
        .and_then(|builder| builder.path(path))
        .and_then(|builder| builder.interface(interface))
        .and_then(|builder| builder.cache_properties(CacheProperties::No).build())
        .map_err(|_| unavailable())
}

fn service(conn: &Connection) -> Result<Proxy<'_>> {
    proxy(
        conn,
        "/org/freedesktop/secrets",
        "org.freedesktop.Secret.Service",
    )
}

fn attributes(id: &str) -> HashMap<&str, &str> {
    HashMap::from([("service", "ai-stp-v2"), ("device_id", id)])
}

fn find(service: &Proxy<'_>, id: &str) -> Result<Option<OwnedObjectPath>> {
    let (mut unlocked, locked): (Vec<OwnedObjectPath>, Vec<OwnedObjectPath>) = service
        .call("SearchItems", &(attributes(id),))
        .map_err(|_| unavailable())?;
    if !locked.is_empty() || unlocked.len() > 1 {
        return Err(unavailable());
    }
    Ok(unlocked.pop())
}

fn session(service: &Proxy<'_>) -> Result<OwnedObjectPath> {
    let (output, session): (OwnedValue, OwnedObjectPath) = service
        .call("OpenSession", &("plain", Value::from("")))
        .map_err(|_| unavailable())?;
    if <&str>::try_from(&output).ok() != Some("") || session.as_str() == "/" {
        return Err(unavailable());
    }
    Ok(session)
}

pub(super) fn read(id: &str) -> Result<Option<Zeroizing<Vec<u8>>>> {
    let conn = connection()?;
    let service = service(&conn)?;
    let Some(path) = find(&service, id)? else {
        return Ok(None);
    };
    let item = proxy(&conn, path.as_str(), "org.freedesktop.Secret.Item")?;
    let session = session(&service)?;
    let (returned_session, parameters, bytes, content_type): Secret = item
        .call("GetSecret", &(&session,))
        .map_err(|_| unavailable())?;
    let bytes = Zeroizing::new(bytes);
    if returned_session != session || !parameters.is_empty() || content_type != "text/plain" {
        return Err(unavailable());
    }
    Ok(Some(bytes))
}

pub(super) fn create(id: &str, value: &str) -> Result<()> {
    let conn = connection()?;
    let service = service(&conn)?;
    if find(&service, id)?.is_some() {
        return Err(super::invalid());
    }
    let collection: OwnedObjectPath = service
        .call("ReadAlias", &("default",))
        .map_err(|_| unavailable())?;
    if collection.as_str() == "/" {
        return Err(unavailable());
    }
    let collection = proxy(
        &conn,
        collection.as_str(),
        "org.freedesktop.Secret.Collection",
    )?;
    if collection
        .get_property::<bool>("Locked")
        .map_err(|_| unavailable())?
    {
        return Err(unavailable());
    }
    let session = session(&service)?;
    let properties = HashMap::from([
        (
            "org.freedesktop.Secret.Item.Label",
            Value::from("ai-stp-v2 device signing key"),
        ),
        (
            "org.freedesktop.Secret.Item.Attributes",
            Value::from(attributes(id)),
        ),
    ]);
    let secret = (&session, &[] as &[u8], value.as_bytes(), "text/plain");
    let (item, prompt): (OwnedObjectPath, OwnedObjectPath) = collection
        .call("CreateItem", &(properties, secret, false))
        .map_err(|_| unavailable())?;
    // A prompt becomes invalid when this connection closes. Never display it.
    if item.as_str() == "/" || prompt.as_str() != "/" {
        return Err(unavailable());
    }
    Ok(())
}
