//! Immutable command descriptors shared by the shell's permission gates.

use ai_stp_desktop_core::{CliRunner, CommandRegistry, MachineHelp, RunError};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

#[derive(Default)]
pub(super) struct RegistryCache(Mutex<Option<(Arc<CommandRegistry>, Instant)>>);

/// Digest re-verification interval: `capabilities` is a subprocess spawn,
/// so checking it on every gated call doubles spawn cost. The digest only
/// changes when the CLI binary is replaced mid-session — a 30 s TTL bounds
/// staleness well inside any realistic upgrade race.
const REGISTRY_TTL: Duration = Duration::from_secs(30);

impl RegistryCache {
    /// Command registry, refreshed whenever the CLI's `registry_digest`
    /// changes (CLI upgrades invalidate cached descriptors).
    pub(super) fn get(&self, runner: &CliRunner) -> Result<Arc<CommandRegistry>, RunError> {
        let cached = self
            .0
            .lock()
            .map_err(|_| RunError::Internal("state poisoned".into()))?
            .clone();
        if let Some((reg, checked_at)) = cached {
            if checked_at.elapsed() < REGISTRY_TTL {
                // A cache hit is not a verification. Moving the timestamp
                // here would keep an actively used registry fresh forever.
                return Ok(reg);
            }
            // Cheap freshness probe outside the lock: `capabilities`
            // carries the live digest.
            let live = match runner.run(&["capabilities".into()]) {
                Ok(env) => {
                    env.ok
                        && env
                            .data
                            .as_ref()
                            .and_then(|d| d.get("registry_digest"))
                            .and_then(|d| d.as_str())
                            == Some(reg.registry_digest.as_str())
                }
                Err(_) => false,
            };
            if live {
                let mut guard = self
                    .0
                    .lock()
                    .map_err(|_| RunError::Internal("state poisoned".into()))?;
                *guard = Some((reg.clone(), Instant::now()));
                return Ok(reg);
            }
        }
        let env = runner.run(&["help".into(), "--agent".into()])?;
        if !env.ok {
            return Err(RunError::Internal(
                env.error
                    .map(|e| e.message)
                    .unwrap_or_else(|| "help --agent failed".into()),
            ));
        }
        let help: MachineHelp = serde_json::from_value(
            env.data
                .ok_or_else(|| RunError::Internal("help --agent: empty data".into()))?,
        )
        .map_err(|e| RunError::Internal(format!("machine-help parse: {e}")))?;
        let reg = Arc::new(CommandRegistry::from_help(&help));
        *self
            .0
            .lock()
            .map_err(|_| RunError::Internal("state poisoned".into()))? =
            Some((reg.clone(), Instant::now()));
        Ok(reg)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    #[test]
    fn registry_reads_share_a_snapshot_without_postponing_verification() {
        let cache = RegistryCache::default();
        let help: MachineHelp =
            serde_json::from_str(include_str!("../../core/tests/fixtures/machine-help.json"))
                .unwrap();
        let reg = Arc::new(CommandRegistry::from_help(&help));
        let checked_at = Instant::now() - Duration::from_secs(1);
        *cache.0.lock().unwrap() = Some((Arc::clone(&reg), checked_at));
        // Fresh reads share descriptors without starting a subprocess.
        // Once expired, a failed probe must not return the stale registry.
        let runner = CliRunner {
            executable: PathBuf::new(),
            env: Vec::new(),
            timeout: Duration::from_secs(1),
        };
        for _ in 0..3 {
            let observed = cache.get(&runner).unwrap();
            assert!(Arc::ptr_eq(&observed, &reg));
            assert_eq!(observed.registry_digest, reg.registry_digest);
            assert_eq!(cache.0.lock().unwrap().as_ref().unwrap().1, checked_at);
        }
        cache.0.lock().unwrap().as_mut().unwrap().1 = Instant::now() - REGISTRY_TTL;
        assert!(cache.get(&runner).is_err());
    }
}
