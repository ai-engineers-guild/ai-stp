//! Independent read/delete observer for the disposable CI Secret Service.
//! All credential creation and replacement is exercised through the product.

use std::{
    cell::RefCell,
    collections::{HashMap, HashSet},
    error::Error,
    fmt,
    time::Duration,
};
use zbus::{
    Connection, Proxy,
    address::{Address, transport::Transport},
    connection::Builder,
    proxy::{self, CacheProperties},
    wire::{OwnedObjectPath, OwnedVariant, Variant},
};

type Result<T> = std::result::Result<T, Box<dyn Error>>;

thread_local! {
    // Observe through our own transport, independent of the product connection.
    // Keep no item, proxy, session or credential value between operations.
    static CONNECTION: RefCell<Option<(String, Connection)>> = const { RefCell::new(None) };
}

#[derive(Debug)]
struct ObserverError {
    stage: &'static str,
    kind: &'static str,
}

impl fmt::Display for ObserverError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "vault observer {}: {}", self.stage, self.kind)
    }
}

impl Error for ObserverError {}

fn failed(stage: &'static str, error: zbus::Error) -> Box<dyn Error> {
    // Free-form remote errors can include attributes or credential payloads.
    let kind = match error {
        zbus::Error::FDO(error) => match *error {
            zbus::fdo::Error::UnknownMethod(_) => "unknown_method",
            zbus::fdo::Error::NoReply(_) => "no_reply",
            zbus::fdo::Error::Timeout(_) | zbus::fdo::Error::TimedOut(_) => "timeout",
            zbus::fdo::Error::ServiceUnknown(_) | zbus::fdo::Error::NameHasNoOwner(_) => {
                "service_absent"
            }
            _ => "standard_remote_error",
        },
        zbus::Error::InputOutput(_) | zbus::Error::Connection(_, _) => "transport",
        zbus::Error::MethodError(_, _, _) => "remote_error",
        _ => "wire_or_connection_error",
    };
    Box::new(ObserverError { stage, kind })
}

async fn connection() -> Result<Connection> {
    if std::env::var("AI_STP_TEST_SECRET_SERVICE").as_deref() != Ok("isolated") {
        return Err("run only through the isolated CI Secret Service fixture".into());
    }
    let address = Address::session().map_err(|error| failed("address", error))?;
    if !matches!(address.transport(), Transport::Unix(_)) {
        return Err("the credential fixture requires a local Unix bus".into());
    }
    let key = address.to_string();
    if let Some(connection) = CONNECTION.with(|cached| {
        cached
            .borrow()
            .as_ref()
            .filter(|(previous, connection)| *previous == key && !connection.is_closed())
            .map(|(_, connection)| connection.clone())
    }) {
        return Ok(connection);
    }
    let connection = Builder::address(address)
        .method_timeout(Duration::from_secs(3))
        .build()
        .await
        .map_err(|error| failed("connect", error))?;
    CONNECTION.with(|cached| *cached.borrow_mut() = Some((key, connection.clone())));
    Ok(connection)
}

async fn proxy<'a>(
    connection: &'a Connection,
    path: &'a str,
    interface: &'a str,
) -> Result<Proxy<'a>> {
    proxy::Builder::new(connection)
        .destination("org.freedesktop.secrets")
        .path(path)
        .interface(interface)
        .cache_properties(CacheProperties::No)
        .build()
        .await
        .map_err(|error| failed("proxy", error))
}

async fn find(service: &Proxy<'_>, name: &str) -> Result<Option<OwnedObjectPath>> {
    // GNOME registers a fresh D-Bus client asynchronously. Observe standard
    // root metadata before the first PKCS#11 lookup on this independent
    // transport; do not replay SearchItems or borrow the product connection.
    let collections: Vec<OwnedObjectPath> = service
        .get_property("Collections")
        .await
        .map_err(|error| failed("service_collections", error))?;
    if collections.len() > 1024
        || collections.iter().any(|path| path.as_str() == "/")
        || collections.iter().collect::<HashSet<_>>().len() != collections.len()
    {
        return Err("the fixture returned invalid bounded collection metadata".into());
    }
    let attributes = if let Some(id) = name.strip_prefix("device-key.") {
        HashMap::from([("service", "ai-stp-v2"), ("device_id", id)])
    } else {
        HashMap::from([("service", "ai-stp-v2"), ("credential_id", name)])
    };
    let (mut unlocked, locked): (Vec<OwnedObjectPath>, Vec<OwnedObjectPath>) = service
        .call("SearchItems", &(attributes,))
        .await
        .map_err(|error| failed("search_items", error))?;
    if !locked.is_empty() || unlocked.len() > 1 {
        return Err("an owned fixture slot is locked or ambiguous".into());
    }
    Ok(unlocked.pop())
}

pub(super) fn read(name: &str) -> Result<Option<Vec<u8>>> {
    finish(zbus::block_on(async {
        let connection = connection().await?;
        let service = proxy(
            &connection,
            "/org/freedesktop/secrets",
            "org.freedesktop.Secret.Service",
        )
        .await?;
        let Some(path) = find(&service, name).await? else {
            return Ok(None);
        };
        let (output, session): (OwnedVariant, OwnedObjectPath) = service
            .call("OpenSession", &("plain", Variant::from("")))
            .await
            .map_err(|error| failed("open_session", error))?;
        if session.as_str() == "/" {
            return Err("the fixture did not open a secret session".into());
        }
        let read: Result<Vec<u8>> = async {
            if <&str>::try_from(&output).ok() != Some("") {
                return Err("the fixture returned invalid plain session parameters".into());
            }
            let item = proxy(&connection, path.as_str(), "org.freedesktop.Secret.Item").await?;
            let (returned, parameters, bytes, _): (OwnedObjectPath, Vec<u8>, Vec<u8>, String) =
                item.call("GetSecret", &(session.clone(),))
                    .await
                    .map_err(|error| failed("get_secret", error))?;
            if returned != session || !parameters.is_empty() || bytes.len() > 65536 {
                return Err("the fixture returned an invalid bounded plain secret".into());
            }
            Ok(bytes)
        }
        .await;
        // Close even after a failed read; retain its original diagnostic.
        let closed: Result<()> = async {
            let session = proxy(
                &connection,
                session.as_str(),
                "org.freedesktop.Secret.Session",
            )
            .await?;
            session
                .call::<_, _, ()>("Close", &())
                .await
                .map_err(|error| failed("close_session", error))
        }
        .await;
        match read {
            Ok(bytes) => {
                closed?;
                Ok(Some(bytes))
            }
            Err(error) => Err(error),
        }
    }))
}

pub(super) fn remove(name: &str) -> Result<()> {
    finish(zbus::block_on(async {
        let connection = connection().await?;
        let service = proxy(
            &connection,
            "/org/freedesktop/secrets",
            "org.freedesktop.Secret.Service",
        )
        .await?;
        let Some(path) = find(&service, name).await? else {
            return Ok(());
        };
        let item = proxy(&connection, path.as_str(), "org.freedesktop.Secret.Item").await?;
        let prompt: OwnedObjectPath = item
            .call("Delete", &())
            .await
            .map_err(|error| failed("delete", error))?;
        if prompt.as_str() != "/" {
            return Err("the fixture must not prompt".into());
        }
        Ok(())
    }))
}

fn finish<T>(result: Result<T>) -> Result<T> {
    if result.is_err() {
        // Do not replay a read or deletion. Only the next independent operation
        // may open another connection after this transport has failed.
        CONNECTION.with(|cached| *cached.borrow_mut() = None);
    }
    result
}
