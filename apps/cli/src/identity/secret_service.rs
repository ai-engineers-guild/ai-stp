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
use crate::error::{Failure, Result};

const SERVICE: &str = "org.freedesktop.secrets";
type Secret = (OwnedObjectPath, Vec<u8>, Vec<u8>, String);

fn unavailable_at(stage: &'static str) -> Failure {
    unavailable().with_details([("credential_stage".into(), stage.into())])
}

fn unavailable_error(stage: &'static str, error: &zbus::Error) -> Failure {
    // Error prose and reply bodies can contain credential attributes or bytes.
    // Only these static categories may cross the public failure boundary.
    let kind = match error {
        zbus::Error::FDO(error) => match error.as_ref() {
            zbus::fdo::Error::NoReply(_) => "no_reply",
            zbus::fdo::Error::Timeout(_) | zbus::fdo::Error::TimedOut(_) => "timeout",
            zbus::fdo::Error::ServiceUnknown(_) | zbus::fdo::Error::NameHasNoOwner(_) => {
                "service_absent"
            }
            zbus::fdo::Error::UnknownObject(_) => "unknown_object",
            zbus::fdo::Error::InvalidArgs(_) => "invalid_arguments",
            zbus::fdo::Error::AccessDenied(_) | zbus::fdo::Error::AuthFailed(_) => "access_denied",
            zbus::fdo::Error::Disconnected(_) => "disconnected",
            zbus::fdo::Error::LimitsExceeded(_) => "resource_limit",
            _ => "standard_remote_error",
        },
        zbus::Error::MethodError(name, _, _) => match name.as_str() {
            "org.freedesktop.Secret.Error.IsLocked" => "secret_locked",
            "org.freedesktop.Secret.Error.NoSession" => "secret_session_absent",
            "org.freedesktop.Secret.Error.NoSuchObject" => "secret_object_absent",
            _ => "remote_error",
        },
        zbus::Error::InputOutput(_) | zbus::Error::Connection(_, _) => "transport",
        zbus::Error::InvalidReply => "invalid_reply",
        zbus::Error::SignatureMismatch(_, _) | zbus::Error::IncorrectType => "wire_type",
        zbus::Error::Handshake(_) => "handshake",
        _ => "other",
    };
    unavailable_at(stage).with_details([("credential_error_kind".into(), kind.into())])
}

async fn connection() -> Result<Connection> {
    let address =
        Address::session().map_err(|error| unavailable_error("session_address", &error))?;
    if !matches!(address.transport(), Transport::Unix(_)) {
        return Err(unavailable_at("session_transport"));
    }
    Builder::address(address)
        .method_timeout(Duration::from_secs(3))
        .build()
        .await
        .map_err(|error| unavailable_error("connect", &error))
}

async fn proxy<'a>(conn: &'a Connection, path: &'a str, interface: &'a str) -> Result<Proxy<'a>> {
    proxy::Builder::new(conn)
        .destination(SERVICE)
        .path(path)
        .interface(interface)
        .cache_properties(CacheProperties::No)
        .build()
        .await
        .map_err(|error| unavailable_error("proxy", &error))
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
        .map_err(|error| unavailable_error("search_items", &error))?;
    if !locked.is_empty() || unlocked.len() > 1 {
        return Err(unavailable_at("search_locked_or_ambiguous"));
    }
    Ok(unlocked.pop())
}

async fn session(service: &Proxy<'_>) -> Result<OwnedObjectPath> {
    let (output, session): (OwnedVariant, OwnedObjectPath) = service
        .call("OpenSession", &("plain", Variant::from("")))
        .await
        .map_err(|error| unavailable_error("open_session", &error))?;
    if <&str>::try_from(&output).ok() != Some("") || session.as_str() == "/" {
        return Err(unavailable_at("open_session_shape"));
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
        .map_err(|error| unavailable_error("get_secret", &error))?;
    let bytes = Zeroizing::new(bytes);
    if returned_session != session || !parameters.is_empty() || content_type != "text/plain" {
        return Err(unavailable_at("get_secret_shape"));
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
            .map_err(|error| unavailable_error("set_secret", &error))?;
        return Ok(());
    }
    if replace {
        return Err(super::invalid());
    }
    let collection: OwnedObjectPath = service
        .call("ReadAlias", &("default",))
        .await
        .map_err(|error| unavailable_error("read_default_alias", &error))?;
    if collection.as_str() == "/" {
        return Err(unavailable_at("default_collection_absent"));
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
        .map_err(|error| unavailable_error("read_collection_lock", &error))?
    {
        return Err(unavailable_at("collection_locked"));
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
        .map_err(|error| unavailable_error("create_item", &error))?;
    // A prompt becomes invalid when this connection closes. Never display it.
    if item.as_str() == "/" || prompt.as_str() != "/" {
        return Err(unavailable_at("create_item_prompt"));
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
    let prompt: OwnedObjectPath = item
        .call("Delete", &())
        .await
        .map_err(|error| unavailable_error("delete_item", &error))?;
    if prompt.as_str() != "/" {
        return Err(unavailable_at("delete_item_prompt"));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn credential_diagnostics_never_expose_remote_error_payloads() {
        for (error, expected) in [
            (
                zbus::Error::FDO(Box::new(zbus::fdo::Error::InvalidArgs(
                    "private-credential-canary".into(),
                ))),
                "invalid_arguments",
            ),
            (
                zbus::Error::FDO(Box::new(zbus::fdo::Error::NoReply(
                    "private-credential-canary".into(),
                ))),
                "no_reply",
            ),
            (
                zbus::Error::Failure("private-credential-canary".into()),
                "other",
            ),
        ] {
            let failure = unavailable_error("search_items", &error);
            assert!(matches!(failure.kind, crate::error::ErrorKind::Unavailable));
            assert_eq!(failure.details["credential_stage"], "search_items");
            assert_eq!(failure.details["credential_error_kind"], expected);
            assert!(!format!("{failure:?}").contains("private-credential-canary"));
        }
    }
}
