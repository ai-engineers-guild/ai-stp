//! Bounded Keychain diagnostics, never native error prose or credential values.

use crate::error::Failure;

fn failure(stage: &'static str, code: Option<i32>) -> Failure {
    let mut failure = super::unavailable().with_details([
        ("credential_stage".into(), stage.into()),
        ("credential_error_kind".into(), "keychain".into()),
    ]);
    if let Some(code) = code {
        failure = failure.with_details([("credential_os_status".into(), code.into())]);
    }
    failure
}

pub(super) fn status(stage: &'static str, error: &security_framework::base::Error) -> Failure {
    failure(stage, Some(error.code()))
}

pub(super) fn keyring(stage: &'static str, error: &keyring_core::Error) -> Failure {
    let code = match error {
        keyring_core::Error::PlatformFailure(source)
        | keyring_core::Error::NoStorageAccess(source) => source
            .downcast_ref::<security_framework::base::Error>()
            .map(|error| error.code()),
        _ => None,
    };
    failure(stage, code)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn keychain_diagnostics_retain_only_stage_and_numeric_status() -> serde_json::Result<()> {
        let native = security_framework::base::Error::from_code(-25308);
        for error in [
            keyring_core::Error::PlatformFailure(Box::new(native)),
            keyring_core::Error::NoStorageAccess(Box::new(native)),
        ] {
            let failure = keyring("read", &error);
            assert_eq!(failure.kind.code(), "AI_STP_DEPENDENCY_UNAVAILABLE");
            assert_eq!(
                serde_json::to_value(&failure.details)?,
                json!({"credential_stage":"read", "credential_error_kind":"keychain",
                    "credential_os_status":-25308})
            );
        }
        let private = keyring_core::Error::PlatformFailure(Box::new(std::io::Error::other(
            "private-native-credential-canary",
        )));
        let failure = keyring("write", &private);
        assert_eq!(failure.details.len(), 2);
        assert!(!format!("{failure:?}").contains("private-native-credential-canary"));
        Ok(())
    }
}
