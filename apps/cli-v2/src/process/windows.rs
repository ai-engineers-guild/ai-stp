//! Inherited lifetime ownership precedes every managed Windows process creation.

use std::sync::OnceLock;

use win_custody::{Job, JobLimits};

use crate::error::Result;

pub(super) fn own_lifetime() -> Result<()> {
    static OWNER: OnceLock<std::result::Result<(), Option<i32>>> = OnceLock::new();
    let result = OWNER.get_or_init(|| {
        let limits = JobLimits::new().kill_on_close(true);
        let create = || {
            let job = Job::create(&limits)?;
            if job.limits()? != limits {
                return Err(std::io::Error::other("job limits were not retained"));
            }
            // This consumes the anonymous, non-inheritable job handle and keeps
            // it open until this process exits. No breakaway flag is enabled.
            // Children inherit membership atomically during CreateProcess,
            // including process-wrap's suspended-before-assignment interval.
            job.assign_current_process()
        };
        create().map_err(|error| error.raw_os_error())
    });
    result.map_err(|code| {
        super::unavailable("Windows process lifetime ownership could not be established")
            .with_details([("os_error".into(), code.into())])
    })
}

#[cfg(test)]
mod tests;
