//! Inspect the held object; never change an existing destination's permissions.

use crate::error::{Failure, Result};
use std::os::windows::io::AsHandle;
use win_custody::{ObjectSecurityDescriptor, OwnedSid, current_user_sid_string};

pub(super) fn private(handle: &impl AsHandle, directory: bool) -> Result<()> {
    let refused = || {
        Failure::precondition(
            "document export requires a Windows ACL limited to the current user, SYSTEM and administrators",
        )
    };
    let user = OwnedSid::from_string(&current_user_sid_string().map_err(|_| refused())?)
        .map_err(|_| refused())?;
    let system = OwnedSid::from_string("S-1-5-18").map_err(|_| refused())?;
    let administrators = OwnedSid::from_string("S-1-5-32-544").map_err(|_| refused())?;
    let creator = OwnedSid::from_string("S-1-3-0").map_err(|_| refused())?;
    // File/directory handles are kernel handles. This safe query binds the
    // owner and DACL to the open object instead of reopening an ambient path.
    let descriptor =
        ObjectSecurityDescriptor::query_kernel_object(handle).map_err(|_| refused())?;
    let owner = descriptor.owner().map_err(|_| refused())?;
    let trusted = [&user, &system, &administrators];
    if !trusted.iter().any(|sid| owner.matches(sid)) {
        return Err(refused());
    }
    let acl = descriptor.dacl().map_err(|_| refused())?;
    if acl.is_empty() {
        return Err(refused());
    }
    for ace in acl.allowed_aces() {
        // Reject unknown flags and all non-allow ACEs (validated by the crate).
        // Creator Owner is safe only as an inherit-only directory template:
        // each resulting child is checked again before writing any content.
        if ace.flags() & !0x1f != 0
            || !(trusted.iter().any(|sid| ace.trustee_matches(sid))
                || (directory && ace.flags() & 0x08 != 0 && ace.trustee_matches(&creator)))
        {
            return Err(refused());
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::files::{document, tree};
    use cap_std::fs::Dir;
    use win_custody::SecurityDescriptor;

    #[test]
    fn inherited_private_document_and_shared_acl_refusal()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let root = tempfile::tempdir()?;
        let user = current_user_sid_string()?;
        // Change ACLs only on this test's new, empty fixture directory.
        let acl = format!("D:P(A;;FA;;;{user})(A;OICIIO;GA;;;CO)(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)");
        SecurityDescriptor::from_sddl(&acl)?.apply_to_tree(root.path(), true)?;
        let directory = Dir::open_ambient_dir(root.path(), cap_std::ambient_authority())?;
        private(&directory, true)?;
        let (output, identity) = tree::destination(&root.path().join("evidence.json"))?;
        let digest = crate::digest::bytes("ai-stp:plan:v1", b"Windows document fixture")?;
        document::unused(&output, &identity)?;
        assert!(!document::publish(&output, &identity, b"signed", &digest)?);
        assert!(!document::publish(&output, &identity, b"signed", &digest)?);
        assert_eq!(std::fs::read(&output)?, b"signed");
        let file = crate::files::open_regular(&directory, std::path::Path::new("evidence.json"))?;
        private(&file, false)?;
        drop(file);

        let shared = format!("D:P(A;OICI;FA;;;{user})(A;OICI;FR;;;WD)");
        SecurityDescriptor::from_sddl(&shared)?
            .apply_to_tree(std::path::Path::new(&output), true)?;
        private(&directory, true)?;
        assert!(document::publish(&output, &identity, b"signed", &digest).is_err());
        assert_eq!(std::fs::read(&output)?, b"signed");
        SecurityDescriptor::from_sddl(&shared)?.apply_to_tree(root.path(), true)?;
        assert!(private(&directory, true).is_err());
        let (absent, identity) = tree::destination(&root.path().join("absent.json"))?;
        assert!(document::unused(&absent, &identity).is_err());
        assert!(document::publish(&absent, &identity, b"never written", &digest).is_err());
        assert!(!std::path::Path::new(&absent).exists());
        assert!(document::publish(&output, &identity, b"signed", &digest).is_err());
        assert_eq!(std::fs::read(&output)?, b"signed");
        let everyone = OwnedSid::from_string("S-1-1-0")?;
        assert!(
            ObjectSecurityDescriptor::query_file(root.path())?
                .dacl()?
                .allowed_aces()
                .any(|ace| ace.trustee_matches(&everyone)),
            "refusal must not repair or replace an existing ACL"
        );
        Ok(())
    }
}
