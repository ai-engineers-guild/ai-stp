//! Transient user-service ownership; no persistent unit or privileged manager.

use std::{
    collections::BTreeMap, fs::File, io::Read, os::fd::AsFd, os::unix::net::UnixStream,
    time::Duration,
};

use zbus::{
    Connection, Proxy,
    address::{Address, transport::Transport},
    connection::Builder,
    proxy,
    proxy::CacheProperties,
    wire::{Fd, OwnedObjectPath, OwnedVariant, Variant},
};

use crate::error::Result;

use super::{SUPERVISOR_FLAG, unavailable};

const DESTINATION: &str = "org.freedesktop.systemd1";
const MANAGER: &str = "org.freedesktop.systemd1.Manager";
const SERVICE: &str = "org.freedesktop.systemd1.Service";

pub(super) struct Service {
    connection: Connection,
    name: String,
    _lease: UnixStream,
}

async fn proxy<'a>(
    connection: &'a Connection,
    path: &'a str,
    interface: &'a str,
) -> Result<Proxy<'a>> {
    proxy::Builder::new(connection)
        .destination(DESTINATION)
        .path(path)
        .interface(interface)
        .cache_properties(CacheProperties::No)
        .build()
        .await
        .map_err(|_| unavailable())
}

impl Service {
    async fn manager(&self) -> Result<Proxy<'_>> {
        proxy(&self.connection, "/org/freedesktop/systemd1", MANAGER).await
    }

    pub(super) fn name(&self) -> &str {
        &self.name
    }

    pub(super) fn attach(&self, pid: u32) -> Result<()> {
        zbus::block_on(async {
            self.manager()
                .await?
                .call::<_, _, ()>(
                    "AttachProcessesToUnit",
                    &(self.name.as_str(), "", vec![pid]),
                )
                .await
                .map_err(|_| unavailable())
        })
    }

    pub(super) fn start(image: &File, timeout: Duration) -> Result<Self> {
        let (mut lease, channel) = UnixStream::pair().map_err(|_| unavailable())?;
        lease
            .set_read_timeout(Some(Duration::from_secs(5)))
            .map_err(|_| unavailable())?;
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
        let connection = zbus::block_on(
            Builder::address(address)
                .method_timeout(Duration::from_secs(3))
                .build(),
        )
        .map_err(|_| unavailable())?;
        // Establish cleanup before submitting the method: a timed-out request
        // may still be accepted. The private lease also closes on every error.
        let service = Self {
            connection,
            name: format!("ai-stp-provider-{}.service", ulid::Ulid::generate()),
            _lease: lease.try_clone().map_err(|_| unavailable())?,
        };
        let null = File::options()
            .write(true)
            .open("/dev/null")
            .map_err(|_| unavailable())?;
        let maximum = u64::try_from((timeout + Duration::from_secs(10)).as_micros())
            .map_err(|_| unavailable())?;
        let policy = vec![
            ("Type", Variant::from("exec")),
            ("ExitType", Variant::from("main")),
            ("RemainAfterExit", Variant::from(false)),
            ("KillMode", Variant::from("control-group")),
            // Required by AttachProcessesToUnit. No cgroup filesystem or bus
            // descriptor is exposed to the sandboxed component.
            ("Delegate", Variant::from(true)),
            ("KillSignal", Variant::from(15i32)),
            ("FinalKillSignal", Variant::from(9i32)),
            ("SendSIGKILL", Variant::from(true)),
            ("Restart", Variant::from("no")),
            (
                "RestartForceExitStatus",
                Variant::new((Vec::<i32>::new(), Vec::<i32>::new())),
            ),
            ("RuntimeMaxUSec", Variant::from(maximum)),
            ("RuntimeRandomizedExtraUSec", Variant::from(0u64)),
            ("TimeoutStartUSec", Variant::from(5_000_000u64)),
            ("TimeoutStopUSec", Variant::from(1_000_000u64)),
            ("TimeoutStopFailureMode", Variant::from("kill")),
        ];
        let mut properties = policy
            .iter()
            .map(|(name, value)| value.try_clone().map(|value| (*name, value)))
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(|_| unavailable())?;
        properties.extend([
            (
                "Description",
                Variant::from("Bounded ai-stp provider worker"),
            ),
            ("CollectMode", Variant::from("inactive-or-failed")),
            (
                "StandardInputFileDescriptor",
                Variant::from(Fd::from(image.as_fd())),
            ),
            (
                "StandardOutputFileDescriptor",
                Variant::from(Fd::from(channel.as_fd())),
            ),
            (
                "StandardErrorFileDescriptor",
                Variant::from(Fd::from(null.as_fd())),
            ),
            (
                "ExecStartEx",
                Variant::new(vec![(
                    "/proc/self/fd/0",
                    vec![
                        "ai-stp-provider-supervisor",
                        SUPERVISOR_FLAG,
                        service.name.as_str(),
                    ],
                    vec!["no-env-expand"],
                )]),
            ),
        ]);
        let auxiliary: Vec<(&str, Vec<(&str, Variant<'_>)>)> = Vec::new();
        // Keep the cleanup guard outside the runtime: errors must leave block_on
        // before Drop drives StopUnit, including a timed-out start request.
        zbus::block_on(async {
            let manager = service.manager().await?;
            let _: OwnedObjectPath = manager
                .call(
                    "StartTransientUnit",
                    &(service.name.as_str(), "fail", properties, auxiliary),
                )
                .await
                .map_err(|_| unavailable())?;
            let path: OwnedObjectPath = manager
                .call("GetUnit", &(service.name.as_str(),))
                .await
                .map_err(|_| unavailable())?;
            let unit = proxy(
                &service.connection,
                path.as_str(),
                "org.freedesktop.systemd1.Unit",
            )
            .await?;
            let execution = proxy(
                &service.connection,
                path.as_str(),
                "org.freedesktop.DBus.Properties",
            )
            .await?;
            let observed: BTreeMap<String, OwnedVariant> = execution
                .call("GetAll", &(SERVICE,))
                .await
                .map_err(|_| unavailable())?;
            if !unit
                .get_property::<bool>("Transient")
                .await
                .map_err(|_| unavailable())?
                || unit
                    .get_property::<String>("CollectMode")
                    .await
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
            Ok(())
        })?;
        drop(channel);
        let mut ready = [0];
        lease.read_exact(&mut ready).map_err(|_| unavailable())?;
        if ready != [1] {
            return Err(unavailable());
        }
        Ok(service)
    }
}

impl Drop for Service {
    fn drop(&mut self) {
        zbus::block_on(async {
            if let Ok(manager) = self.manager().await {
                let _: zbus::Result<OwnedObjectPath> = manager
                    .call("StopUnit", &(self.name.as_str(), "replace"))
                    .await;
            }
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        error::Error,
        io::BufRead,
        process::{Child, Command, Stdio},
    };

    struct Bus(Child);

    impl Drop for Bus {
        fn drop(&mut self) {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }

    #[test]
    fn failed_start_cleans_up_outside_the_bus_runtime() -> std::result::Result<(), Box<dyn Error>> {
        const CHILD: &str = "AI_STP_TEST_SERVICE_WITHOUT_MANAGER";
        if std::env::var_os(CHILD).is_some() {
            let image = File::open(std::env::current_exe()?)?;
            assert!(Service::start(&image, Duration::from_secs(1)).is_err());
            return Ok(());
        }
        let temporary = tempfile::tempdir()?;
        let config = temporary.path().join("bus.conf");
        std::fs::write(
            &config,
            "<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen><auth>EXTERNAL</auth><policy context=\"default\"><allow own=\"*\"/><allow send_destination=\"*\"/><allow receive_sender=\"*\"/></policy></busconfig>",
        )?;
        let child = Command::new("dbus-daemon")
            .arg("--config-file")
            .arg(config)
            .args(["--nofork", "--print-address=1"])
            .stdout(Stdio::piped())
            .spawn()?;
        let mut bus = Bus(child);
        let output = bus.0.stdout.take().ok_or("bus address pipe is missing")?;
        let mut address = String::new();
        std::io::BufReader::new(output).read_line(&mut address)?;
        assert!(address.starts_with("unix:"));
        let result = Command::new(std::env::current_exe()?)
            .args([
                "--exact",
                "process::linux::service::tests::failed_start_cleans_up_outside_the_bus_runtime",
                "--nocapture",
            ])
            .env(CHILD, "1")
            .env("DBUS_SESSION_BUS_ADDRESS", address.trim())
            .output()?;
        assert!(
            result.status.success(),
            "{}{}",
            String::from_utf8_lossy(&result.stdout),
            String::from_utf8_lossy(&result.stderr)
        );
        assert!(String::from_utf8_lossy(&result.stdout).contains("1 passed"));
        Ok(())
    }
}
