//! Independent read/delete observer for the disposable CI Secret Service.
//! All credential creation and replacement is exercised through the product.

use std::{collections::HashMap, error::Error, time::Duration};
use zbus::{
    Connection, Proxy,
    address::{Address, transport::Transport},
    connection::Builder,
    proxy::{self, CacheProperties},
    wire::{OwnedObjectPath, OwnedVariant, Variant},
};

type Result<T> = std::result::Result<T, Box<dyn Error>>;

async fn connection() -> Result<Connection> {
    if std::env::var("AI_STP_TEST_SECRET_SERVICE").as_deref() != Ok("isolated") {
        return Err("run only through the isolated CI Secret Service fixture".into());
    }
    let address = Address::session()?;
    if !matches!(address.transport(), Transport::Unix(_)) {
        return Err("the credential fixture requires a local Unix bus".into());
    }
    Ok(Builder::address(address)
        .method_timeout(Duration::from_secs(3))
        .build()
        .await?)
}

async fn proxy<'a>(
    connection: &'a Connection,
    path: &'a str,
    interface: &'a str,
) -> Result<Proxy<'a>> {
    Ok(proxy::Builder::new(connection)
        .destination("org.freedesktop.secrets")
        .path(path)
        .interface(interface)
        .cache_properties(CacheProperties::No)
        .build()
        .await?)
}

async fn find(service: &Proxy<'_>, name: &str) -> Result<Option<OwnedObjectPath>> {
    let attributes = if let Some(id) = name.strip_prefix("device-key.") {
        HashMap::from([("service", "ai-stp-v2"), ("device_id", id)])
    } else {
        HashMap::from([("service", "ai-stp-v2"), ("credential_id", name)])
    };
    let (mut unlocked, locked): (Vec<OwnedObjectPath>, Vec<OwnedObjectPath>) =
        service.call("SearchItems", &(attributes,)).await?;
    if !locked.is_empty() || unlocked.len() > 1 {
        return Err("an owned fixture slot is locked or ambiguous".into());
    }
    Ok(unlocked.pop())
}

pub(super) fn read(name: &str) -> Result<Option<Vec<u8>>> {
    zbus::block_on(async {
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
        let (_, session): (OwnedVariant, OwnedObjectPath) = service
            .call("OpenSession", &("plain", Variant::from("")))
            .await?;
        let item = proxy(&connection, path.as_str(), "org.freedesktop.Secret.Item").await?;
        let (returned_session, parameters, bytes, _): (OwnedObjectPath, Vec<u8>, Vec<u8>, String) =
            item.call("GetSecret", &(session.clone(),)).await?;
        if returned_session != session || !parameters.is_empty() || bytes.len() > 65536 {
            return Err("the fixture returned an invalid bounded plain secret".into());
        }
        let session = proxy(
            &connection,
            session.as_str(),
            "org.freedesktop.Secret.Session",
        )
        .await?;
        let _: () = session.call("Close", &()).await?;
        Ok(Some(bytes))
    })
}

pub(super) fn remove(name: &str) -> Result<()> {
    zbus::block_on(async {
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
        let prompt: OwnedObjectPath = item.call("Delete", &()).await?;
        if prompt.as_str() != "/" {
            return Err("the fixture must not prompt".into());
        }
        Ok(())
    })
}
