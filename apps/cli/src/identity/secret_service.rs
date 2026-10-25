//! Noninteractive Secret Service over the local Unix session bus.
//!
//! The standard `plain` session avoids custom cryptography. Bus transport must be
//! local; at-rest protection belongs to the user's existing credential service.
//! No Unlock, Prompt, CreateCollection or backend fallback is permitted.
//! Device keys are immutable until explicit retirement; account replacement is explicit.

use std::{collections::HashMap, time::Duration};
use zbus::{
    Connection, Proxy,
    address::{Address, transport::Transport},
    connection::Builder,
    proxy,
    proxy::CacheProperties,
    wire::{OwnedObjectPath, OwnedVariant, Variant},
};
use zeroize::Zeroizing;

use super::credentials::unavailable;
use crate::error::Result;

const SERVICE: &str = "org.freedesktop.secrets";
type Secret = (OwnedObjectPath, Vec<u8>, Vec<u8>, String);

async fn connection() -> Result<Connection> {
    let address = Address::session().map_err(|_| unavailable())?;
    if !matches!(address.transport(), Transport::Unix(_)) {
        return Err(unavailable());
    }
    Builder::address(address)
        .method_timeout(Duration::from_secs(3))
        .build()
        .await
        .map_err(|_| unavailable())
}

async fn proxy<'a>(conn: &'a Connection, path: &'a str, interface: &'a str) -> Result<Proxy<'a>> {
    proxy::Builder::new(conn)
        .destination(SERVICE)
        .path(path)
        .interface(interface)
        .cache_properties(CacheProperties::No)
        .build()
        .await
        .map_err(|_| unavailable())
}

async fn service(conn: &Connection) -> Result<Proxy<'_>> {
    proxy(
        conn,
        "/org/freedesktop/secrets",
        "org.freedesktop.Secret.Service",
    )
    .await
}

fn attributes(id: &str) -> HashMap<&str, &str> {
    // Keep the original device-key lookup compatible. Account slots have a
    // separate attribute and cannot collide with an existing signing key.
    if let Some(device) = id.strip_prefix("device-key.") {
        HashMap::from([("service", "ai-stp-v2"), ("device_id", device)])
    } else {
        HashMap::from([("service", "ai-stp-v2"), ("credential_id", id)])
    }
}

async fn find(service: &Proxy<'_>, id: &str) -> Result<Option<OwnedObjectPath>> {
    find_attributes(service, attributes(id)).await
}

async fn find_attributes(
    service: &Proxy<'_>,
    selected: HashMap<&str, &str>,
) -> Result<Option<OwnedObjectPath>> {
    let (mut unlocked, locked): (Vec<OwnedObjectPath>, Vec<OwnedObjectPath>) = service
        .call("SearchItems", &(selected,))
        .await
        .map_err(|_| unavailable())?;
    if !locked.is_empty() || unlocked.len() > 1 {
        return Err(unavailable());
    }
    Ok(unlocked.pop())
}

async fn session(service: &Proxy<'_>) -> Result<OwnedObjectPath> {
    let (output, session): (OwnedVariant, OwnedObjectPath) = service
        .call("OpenSession", &("plain", Variant::from("")))
        .await
        .map_err(|_| unavailable())?;
    if <&str>::try_from(&output).ok() != Some("") || session.as_str() == "/" {
        return Err(unavailable());
    }
    Ok(session)
}

pub(super) fn read(id: &str) -> Result<Option<Zeroizing<Vec<u8>>>> {
    zbus::block_on(read_attributes(attributes(id)))
}

pub(super) fn read_legacy(id: &str) -> Result<Option<Zeroizing<Vec<u8>>>> {
    zbus::block_on(read_attributes(HashMap::from([
        ("service", "ai-stp"),
        ("username", id),
    ])))
}

async fn read_attributes(selected: HashMap<&str, &str>) -> Result<Option<Zeroizing<Vec<u8>>>> {
    let conn = connection().await?;
    let service = service(&conn).await?;
    let Some(path) = find_attributes(&service, selected).await? else {
        return Ok(None);
    };
    let item = proxy(&conn, path.as_str(), "org.freedesktop.Secret.Item").await?;
    let session = session(&service).await?;
    let (returned_session, parameters, bytes, content_type): Secret = item
        .call("GetSecret", &(&session,))
        .await
        .map_err(|_| unavailable())?;
    let bytes = Zeroizing::new(bytes);
    if returned_session != session || !parameters.is_empty() || content_type != "text/plain" {
        return Err(unavailable());
    }
    Ok(Some(bytes))
}

pub(super) fn write(id: &str, value: &str, replace: bool) -> Result<()> {
    zbus::block_on(write_inner(id, value, replace))
}

async fn write_inner(id: &str, value: &str, replace: bool) -> Result<()> {
    let conn = connection().await?;
    let service = service(&conn).await?;
    if let Some(path) = find(&service, id).await? {
        if !replace {
            return Err(super::invalid());
        }
        let item = proxy(&conn, path.as_str(), "org.freedesktop.Secret.Item").await?;
        let session = session(&service).await?;
        let secret = (&session, &[] as &[u8], value.as_bytes(), "text/plain");
        let (): () = item
            .call("SetSecret", &(secret,))
            .await
            .map_err(|_| unavailable())?;
        return Ok(());
    }
    if replace {
        return Err(super::invalid());
    }
    let collection: OwnedObjectPath = service
        .call("ReadAlias", &("default",))
        .await
        .map_err(|_| unavailable())?;
    if collection.as_str() == "/" {
        return Err(unavailable());
    }
    let collection = proxy(
        &conn,
        collection.as_str(),
        "org.freedesktop.Secret.Collection",
    )
    .await?;
    if collection
        .get_property::<bool>("Locked")
        .await
        .map_err(|_| unavailable())?
    {
        return Err(unavailable());
    }
    let session = session(&service).await?;
    let properties = HashMap::from([
        (
            "org.freedesktop.Secret.Item.Label",
            Variant::from(if id.starts_with("device-key.") {
                "ai-stp-v2 device signing key"
            } else {
                "ai-stp-v2 account credential"
            }),
        ),
        (
            "org.freedesktop.Secret.Item.Attributes",
            Variant::from(attributes(id)),
        ),
    ]);
    let secret = (&session, &[] as &[u8], value.as_bytes(), "text/plain");
    let (item, prompt): (OwnedObjectPath, OwnedObjectPath) = collection
        .call("CreateItem", &(properties, secret, false))
        .await
        .map_err(|_| unavailable())?;
    // A prompt becomes invalid when this connection closes. Never display it.
    if item.as_str() == "/" || prompt.as_str() != "/" {
        return Err(unavailable());
    }
    Ok(())
}

pub(super) fn remove(id: &str) -> Result<()> {
    zbus::block_on(remove_attributes(attributes(id)))
}

pub(super) fn remove_legacy(id: &str) -> Result<()> {
    zbus::block_on(remove_attributes(HashMap::from([
        ("service", "ai-stp"),
        ("username", id),
    ])))
}

async fn remove_attributes(selected: HashMap<&str, &str>) -> Result<()> {
    let conn = connection().await?;
    let service = service(&conn).await?;
    let Some(path) = find_attributes(&service, selected).await? else {
        return Ok(());
    };
    let item = proxy(&conn, path.as_str(), "org.freedesktop.Secret.Item").await?;
    let prompt: OwnedObjectPath = item.call("Delete", &()).await.map_err(|_| unavailable())?;
    if prompt.as_str() != "/" {
        return Err(unavailable());
    }
    Ok(())
}
