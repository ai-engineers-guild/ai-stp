//! Transient user-service ownership; no persistent unit or privileged manager.

use std::{
    collections::BTreeMap, fs::File, os::fd::AsFd, os::unix::net::UnixStream, time::Duration,
};

use zbus::{
    address::{Address, transport::Transport},
    blocking::{Connection, Proxy, connection::Builder, proxy},
    proxy::CacheProperties,
    zvariant::{Fd, OwnedObjectPath, OwnedValue, Value},
};

use crate::error::Result;

use super::{FLAG, unavailable};

const DESTINATION: &str = "org.freedesktop.systemd1";
const MANAGER: &str = "org.freedesktop.systemd1.Manager";
const SERVICE: &str = "org.freedesktop.systemd1.Service";

pub(super) struct Service {
    connection: Connection,
    name: String,
}

fn proxy<'a>(connection: &'a Connection, path: &'a str, interface: &'a str) -> Result<Proxy<'a>> {
    proxy::Builder::new(connection)
        .destination(DESTINATION)
        .and_then(|builder| builder.path(path))
        .and_then(|builder| builder.interface(interface))
        .and_then(|builder| builder.cache_properties(CacheProperties::No).build())
        .map_err(|_| unavailable())
}

impl Service {
    fn manager(&self) -> Result<Proxy<'_>> {
        proxy(&self.connection, "/org/freedesktop/systemd1", MANAGER)
    }

    pub(super) fn start(image: &File, channel: &UnixStream, timeout: Duration) -> Result<Self> {
        let address = Address::session()
            .or_else(|_| {
                Address::try_from(
                    format!(
                        "unix:path=/run/user/{}/bus",
                        rustix::process::geteuid().as_raw()
                    )
                    .as_str(),
                )
            })
            .map_err(|_| unavailable())?;
        if !matches!(address.transport(), Transport::Unix(_)) {
            return Err(unavailable());
        }
        let connection = Builder::address(address)
            .map_err(|_| unavailable())?
            .method_timeout(Duration::from_secs(3))
            .build()
            .map_err(|_| unavailable())?;
        // Establish cleanup before submitting the method: a timed-out request
        // may still be accepted. The private lease also closes on every error.
        let service = Self {
            connection,
            name: format!("ai-stp-provider-{}.service", ulid::Ulid::generate()),
        };
        let null = File::options()
            .write(true)
            .open("/dev/null")
            .map_err(|_| unavailable())?;
        let maximum = u64::try_from((timeout + Duration::from_secs(10)).as_micros())
            .map_err(|_| unavailable())?;
        let policy = vec![
            ("Type", Value::from("exec")),
            ("ExitType", Value::from("main")),
            ("RemainAfterExit", Value::from(false)),
            ("KillMode", Value::from("control-group")),
            ("KillSignal", Value::from(15i32)),
            ("FinalKillSignal", Value::from(9i32)),
            ("SendSIGKILL", Value::from(true)),
            ("Restart", Value::from("no")),
            (
                "RestartForceExitStatus",
                Value::new((Vec::<i32>::new(), Vec::<i32>::new())),
            ),
            ("RuntimeMaxUSec", Value::from(maximum)),
            ("RuntimeRandomizedExtraUSec", Value::from(0u64)),
            ("TimeoutStartUSec", Value::from(5_000_000u64)),
            ("TimeoutStopUSec", Value::from(1_000_000u64)),
            ("TimeoutStopFailureMode", Value::from("kill")),
        ];
        let mut properties = policy
            .iter()
            .map(|(name, value)| value.try_clone().map(|value| (*name, value)))
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(|_| unavailable())?;
        properties.extend([
            ("Description", Value::from("Bounded ai-stp provider worker")),
            ("CollectMode", Value::from("inactive-or-failed")),
            (
                "StandardInputFileDescriptor",
                Value::from(Fd::from(image.as_fd())),
            ),
            (
                "StandardOutputFileDescriptor",
                Value::from(Fd::from(channel.as_fd())),
            ),
            (
                "StandardErrorFileDescriptor",
                Value::from(Fd::from(null.as_fd())),
            ),
            (
                "ExecStartEx",
                Value::new(vec![(
                    "/proc/self/fd/0",
                    vec!["ai-stp-provider-worker", FLAG, service.name.as_str()],
                    vec!["no-env-expand"],
                )]),
            ),
        ]);
        let auxiliary: Vec<(&str, Vec<(&str, Value<'_>)>)> = Vec::new();
        let manager = service.manager()?;
        let _: OwnedObjectPath = manager
            .call(
                "StartTransientUnit",
                &(service.name.as_str(), "fail", properties, auxiliary),
            )
            .map_err(|_| unavailable())?;
        let path: OwnedObjectPath = manager
            .call("GetUnit", &(service.name.as_str(),))
            .map_err(|_| unavailable())?;
        let unit = proxy(
            &service.connection,
            path.as_str(),
            "org.freedesktop.systemd1.Unit",
        )?;
        let execution = proxy(
            &service.connection,
            path.as_str(),
            "org.freedesktop.DBus.Properties",
        )?;
        let observed: BTreeMap<String, OwnedValue> = execution
            .call("GetAll", &(SERVICE,))
            .map_err(|_| unavailable())?;
        if !unit
            .get_property::<bool>("Transient")
            .map_err(|_| unavailable())?
            || unit
                .get_property::<String>("CollectMode")
                .map_err(|_| unavailable())?
                != "inactive-or-failed"
            || !policy.iter().all(|(name, expected)| {
                observed
                    .get(*name)
                    .is_some_and(|actual| **actual == *expected)
            })
        {
            return Err(unavailable());
        }
        drop(execution);
        drop(unit);
        drop(manager);
        Ok(service)
    }
}

impl Drop for Service {
    fn drop(&mut self) {
        if let Ok(manager) = self.manager() {
            let _: zbus::Result<OwnedObjectPath> =
                manager.call("StopUnit", &(self.name.as_str(), "replace"));
        }
    }
}
