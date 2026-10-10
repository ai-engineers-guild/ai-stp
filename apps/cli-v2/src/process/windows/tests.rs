use std::{
    env,
    error::Error,
    ffi::OsString,
    fs,
    os::windows::process::CommandExt,
    path::Path,
    process::{Child, Command, Stdio},
    thread,
    time::{Duration, Instant},
};

use winsafe::{HPROCESS, co};

const CASE: &str = "process::windows::tests::parent_death_owns_running_and_unassigned_children";
const STAGE: &str = "AI_STP_JOB_PROOF_STAGE";
const ROOT: &str = "AI_STP_JOB_PROOF_ROOT";
const CREATE_SUSPENDED: u32 = 0x4;
const CREATE_BREAKAWAY_FROM_JOB: u32 = 0x0100_0000;

struct OwnedChild(Child);
impl Drop for OwnedChild {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn command(root: &Path, stage: &str) -> std::io::Result<Command> {
    let mut command = Command::new(env::current_exe()?);
    command
        .args(["--exact", CASE, "--nocapture"])
        .env(STAGE, stage)
        .env(ROOT, root)
        .stdin(Stdio::null())
        .stdout(Stdio::null());
    Ok(command)
}

fn fixture(root: &Path, stage: &str) -> Result<(), Box<dyn Error>> {
    match stage {
        "suspended" => {
            super::own_lifetime()?;
            super::own_lifetime()?;
            // Model the exact creation gap: no per-command job assignment and
            // no user instruction has run in this child before the owner dies.
            let child = OwnedChild(
                command(root, "never_run")?
                    .creation_flags(CREATE_SUSPENDED)
                    .spawn()?,
            );
            fs::write(root.join("child"), child.0.id().to_string())?;
            thread::sleep(Duration::from_secs(30));
        }
        "running" => {
            let executable = env::current_exe()?;
            let arguments = ["--exact", CASE, "--nocapture"].map(OsString::from);
            let environment: Vec<_> = env::vars_os()
                .filter(|(name, _)| {
                    name.to_str().is_some_and(|name| {
                        ["SYSTEMROOT", "WINDIR", "TEMP", "TMP"]
                            .iter()
                            .any(|key| name.eq_ignore_ascii_case(key))
                    })
                })
                .chain([(STAGE.into(), "child".into()), (ROOT.into(), root.into())])
                .collect();
            crate::process::run(crate::process::Request {
                executable: &executable,
                arguments: &arguments,
                directory: root,
                environment: &environment,
                timeout: Duration::from_secs(30),
                output_limit: 4096,
            })?;
            return Err("the owner completed before forced termination".into());
        }
        "child" => {
            if let Ok(child) = command(root, "grandchild")?
                .creation_flags(CREATE_BREAKAWAY_FROM_JOB)
                .spawn()
            {
                drop(OwnedChild(child));
                return Err("a child escaped lifetime ownership".into());
            }
            let _child = OwnedChild(command(root, "grandchild")?.spawn()?);
            fs::write(root.join("child"), std::process::id().to_string())?;
            thread::sleep(Duration::from_secs(30));
        }
        "grandchild" => {
            fs::write(root.join("grandchild"), std::process::id().to_string())?;
            thread::sleep(Duration::from_secs(30));
        }
        _ => return Err("a suspended child unexpectedly executed".into()),
    }
    Ok(())
}

#[test]
fn parent_death_owns_running_and_unassigned_children() -> Result<(), Box<dyn Error>> {
    if let Ok(stage) = env::var(STAGE) {
        return fixture(
            Path::new(&env::var_os(ROOT).ok_or("missing proof root")?),
            &stage,
        );
    }
    for stage in ["suspended", "running"] {
        let root = tempfile::tempdir()?;
        let mut owner = OwnedChild(command(root.path(), stage)?.spawn()?);
        let names: &[&str] = if stage == "running" {
            &["child", "grandchild"]
        } else {
            &["child"]
        };
        let until = Instant::now() + Duration::from_secs(15);
        let mut handles = Vec::new();
        for name in names {
            let path = root.path().join(name);
            let pid = loop {
                if let Ok(value) = fs::read_to_string(&path)
                    && let Ok(pid) = value.parse::<u32>()
                {
                    break pid;
                }
                if Instant::now() >= until || owner.0.try_wait()?.is_some() {
                    return Err("the owned process did not report its identity".into());
                }
                thread::sleep(Duration::from_millis(5));
            };
            let handle = HPROCESS::OpenProcess(
                co::PROCESS::SYNCHRONIZE | co::PROCESS::TERMINATE,
                false,
                pid,
            )?;
            assert_eq!(handle.WaitForSingleObject(Some(0))?, co::WAIT::TIMEOUT);
            handles.push(handle);
        }
        owner.0.kill()?;
        owner.0.wait()?;
        for handle in handles {
            let observed = handle.WaitForSingleObject(Some(10_000))?;
            if observed != co::WAIT::OBJECT_0 {
                handle.TerminateProcess(1)?;
            }
            assert_eq!(observed, co::WAIT::OBJECT_0, "{stage} child survived");
        }
    }
    Ok(())
}
