//! Noninteractive Secret Service over the local Unix session bus.
//!
//! The standard `plain` session avoids custom cryptography. Bus transport must be
//! local; at-rest protection belongs to the user's existing credential service.
//! No Unlock, Prompt, CreateCollection or backend fallback is permitted.
//! Device keys are immutable until explicit retirement; account replacement is explicit.

use std::{
    cell::RefCell,
    collections::{HashMap, HashSet},
    time::Duration,
};
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

thread_local! {
    // Retain transport only, never credential values, proxies or secret sessions.
    // A different bus address cannot inherit the previous session's connection.
    static CONNECTION: RefCell<Option<(String, Connection)>> = const { RefCell::new(None) };
}

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
            zbus::fdo::Error::UnknownMethod(_) => "unknown_method",
            zbus::fdo::Error::Failed(_) => "remote_failure",
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
    connection_at(address).await
}

async fn connection_at(address: Address) -> Result<Connection> {
    if !matches!(address.transport(), Transport::Unix(_)) {
        return Err(unavailable_at("session_transport"));
    }
    let key = address.to_string();
    if let Some(held) = CONNECTION.with(|cached| {
        cached
            .borrow()
            .as_ref()
            .filter(|(previous, connection)| *previous == key && !connection.is_closed())
            .map(|(_, connection)| connection.clone())
    }) {
        return Ok(held);
    }
    // Independent calls stay concurrent. An error is never converted to
    // credential absence or retried within the operation.
    let connection = Builder::address(address)
        .method_timeout(Duration::from_secs(3))
        .build()
        .await
        .map_err(|error| unavailable_error("connect", &error))?;
    CONNECTION.with(|cached| *cached.borrow_mut() = Some((key, connection.clone())));
    Ok(connection)
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
    let service = proxy(
        conn,
        "/org/freedesktop/secrets",
        "org.freedesktop.Secret.Service",
    )
    .await?;
    // Complete standard root-proxy initialization before a per-client PKCS#11
    // operation. GNOME registers new clients asynchronously (upstream !112);
    // calling SearchItems/OpenSession immediately after connecting can race it.
    // Root Collections metadata needs no secret session, unlock or prompt.
    // Read it explicitly because all proxies otherwise disable property caches.
    let collections: Vec<OwnedObjectPath> = service
        .get_property("Collections")
        .await
        .map_err(|error| unavailable_error("service_collections", &error))?;
    if collections.len() > 1024
        || collections.iter().any(|path| path.as_str() == "/")
        || collections.iter().collect::<HashSet<_>>().len() != collections.len()
    {
        return Err(unavailable_at("service_collections_shape"));
    }
    Ok(service)
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

async fn finish_session<T>(
    conn: &Connection,
    session: &OwnedObjectPath,
    result: Result<T>,
) -> Result<T> {
    let closed = async {
        let session = proxy(conn, session.as_str(), "org.freedesktop.Secret.Session").await?;
        session
            .call::<_, _, ()>("Close", &())
            .await
            .map_err(|error| unavailable_error("close_session", &error))
    }
    .await;
    match result {
        Ok(value) => {
            closed?;
            Ok(value)
        }
        Err(error) => Err(error),
    }
}

fn finish<T>(result: Result<T>) -> Result<T> {
    if result.is_err() {
        // Release the failed transport, including any unresolved prompt or
        // session. The next independent operation may connect afresh.
        CONNECTION.with(|cached| *cached.borrow_mut() = None);
    }
    result
}

pub(super) fn read(id: &str) -> Result<Option<Zeroizing<Vec<u8>>>> {
    finish(zbus::block_on(read_attributes(attributes(id))))
}

pub(super) fn read_legacy(id: &str) -> Result<Option<Zeroizing<Vec<u8>>>> {
    finish(zbus::block_on(read_attributes(HashMap::from([
        ("service", "ai-stp"),
        ("username", id),
    ]))))
}

async fn read_attributes(selected: HashMap<&str, &str>) -> Result<Option<Zeroizing<Vec<u8>>>> {
    let conn = connection().await?;
    let service = service(&conn).await?;
    let Some(path) = find_attributes(&service, selected).await? else {
        return Ok(None);
    };
    let item = proxy(&conn, path.as_str(), "org.freedesktop.Secret.Item").await?;
    let session = session(&service).await?;
    let result = async {
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
    .await;
    finish_session(&conn, &session, result).await
}

pub(super) fn write(id: &str, value: &str, replace: bool) -> Result<()> {
    finish(zbus::block_on(write_inner(id, value, replace)))
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
        let result = item
            .call("SetSecret", &(secret,))
            .await
            .map_err(|error| unavailable_error("set_secret", &error));
        return finish_session(&conn, &session, result).await;
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
    let result = async {
        let (item, prompt): (OwnedObjectPath, OwnedObjectPath) = collection
            .call("CreateItem", &(properties, secret, false))
            .await
            .map_err(|error| unavailable_error("create_item", &error))?;
        // A refusal releases the cached connection and invalidates the prompt.
        // Never display it or treat it as a completed credential write.
        if item.as_str() == "/" || prompt.as_str() != "/" {
            return Err(unavailable_at("create_item_prompt"));
        }
        Ok(())
    }
    .await;
    finish_session(&conn, &session, result).await
}

pub(super) fn remove(id: &str) -> Result<()> {
    finish(zbus::block_on(remove_attributes(attributes(id))))
}

pub(super) fn remove_legacy(id: &str) -> Result<()> {
    finish(zbus::block_on(remove_attributes(HashMap::from([
        ("service", "ai-stp"),
        ("username", id),
    ]))))
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
    #[ignore = "requires the isolated CI Secret Service bus"]
    fn transport_reuse_stays_with_the_exact_existing_unix_bus() -> Result<()> {
        assert_eq!(
            std::env::var("AI_STP_TEST_SECRET_SERVICE").as_deref(),
            Ok("isolated")
        );
        zbus::block_on(async {
            let first = connection().await?;
            let second = connection().await?;
            assert_eq!(first.unique_name(), second.unique_name());
            assert!(first.unique_name().is_some());
            let missing = std::path::PathBuf::from(
                std::env::var_os("AI_STP_TEST_SECRET_SERVICE_ROOT")
                    .ok_or_else(|| unavailable_at("fixture_root"))?,
            )
            .join("absent-bus");
            let address: Address = format!("unix:path={}", missing.display())
                .parse()
                .map_err(|error| unavailable_error("fixture_address", &error))?;
            assert!(
                connection_at(address).await.is_err(),
                "a different address reused the original bus"
            );
            let third = connection().await?;
            assert_eq!(first.unique_name(), third.unique_name());
            let service = service(&third).await?;
            let session = session(&service).await?;
            finish_session(&third, &session, Ok(())).await?;
            let closed = proxy(&third, session.as_str(), "org.freedesktop.Secret.Session").await?;
            assert!(closed.call::<_, _, ()>("Close", &()).await.is_err());
            Ok(())
        })
    }

    #[test]
    #[ignore = "requires the isolated CI Secret Service bus"]
    fn fresh_concurrent_clients_initialize_before_first_credential_lookup() -> Result<()> {
        assert_eq!(
            std::env::var("AI_STP_TEST_SECRET_SERVICE").as_deref(),
            Ok("isolated")
        );
        let names = std::thread::scope(|scope| {
            let workers = (0..8)
                .map(|_| {
                    scope.spawn(|| -> Result<Vec<String>> {
                        let mut names = Vec::new();
                        for _ in 0..25 {
                            // Each iteration must exercise a genuinely new bus
                            // client, without a failed-call retry or a delay.
                            CONNECTION.with(|cached| *cached.borrow_mut() = None);
                            names.push(zbus::block_on(async {
                                let conn = connection().await?;
                                let name = conn
                                    .unique_name()
                                    .ok_or_else(|| unavailable_at("fixture_unique_name"))?
                                    .to_string();
                                let service = service(&conn).await?;
                                assert!(
                                    find_attributes(
                                        &service,
                                        HashMap::from([
                                            ("service", "ai-stp-isolated-absent-probe"),
                                            ("credential_id", "new-client-admission"),
                                        ]),
                                    )
                                    .await?
                                    .is_none()
                                );
                                Ok(name)
                            })?);
                        }
                        CONNECTION.with(|cached| *cached.borrow_mut() = None);
                        Ok(names)
                    })
                })
                .collect::<Vec<_>>();
            workers
                .into_iter()
                .map(|worker| {
                    worker
                        .join()
                        .map_err(|_| unavailable_at("fixture_client_panic"))?
                })
                .collect::<Result<Vec<_>>>()
        })?;
        let names = names.into_iter().flatten().collect::<HashSet<_>>();
        assert_eq!(names.len(), 200, "fresh client qualification was bypassed");
        Ok(())
    }

    #[test]
    fn credential_diagnostics_never_expose_remote_error_payloads() {
        for (error, expected) in [
            (
                zbus::Error::FDO(Box::new(zbus::fdo::Error::UnknownMethod(
                    "private-credential-canary".into(),
                ))),
                "unknown_method",
            ),
            (
                zbus::Error::FDO(Box::new(zbus::fdo::Error::Failed(
                    "private-credential-canary".into(),
                ))),
                "remote_failure",
            ),
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
