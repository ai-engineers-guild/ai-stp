//! Qualify the actual held object before selecting a new durable identity format.

use std::{error::Error, fs};

use cap_std::fs::Dir;

#[cfg(unix)]
fn identity(directory: &Dir) -> std::io::Result<(u64, u128)> {
    use cap_fs_ext::MetadataExt;

    let metadata = directory.dir_metadata()?;
    Ok((metadata.dev(), u128::from(metadata.ino())))
}

#[cfg(windows)]
fn identity(directory: &Dir) -> std::io::Result<(u64, u128)> {
    // The reviewed crate queries FileIdInfo from this open handle. It neither
    // reopens an ambient pathname nor falls back to a truncated 64-bit ID.
    let value = fs_id::FileID::new(directory)?;
    Ok((value.storage_id(), value.internal_file_id()))
}

#[test]
fn directory_identity_survives_close_rename_reopen_and_distinguishes_copies_and_replacements()
-> Result<(), Box<dyn Error>> {
    let fixture = tempfile::tempdir()?;
    let original = fixture.path().join("original");
    let destination = fixture.path().join("moved");
    let copied = fixture.path().join("copied");
    let canary = b"unowned identity fixture\n";
    fs::create_dir(&original)?;
    fs::write(original.join("keep"), canary)?;

    let held = Dir::open_ambient_dir(&original, cap_std::ambient_authority())?;
    let alias = held.try_clone()?;
    let independently_opened = Dir::open_ambient_dir(&original, cap_std::ambient_authority())?;
    let before = identity(&held)?;
    assert_eq!(identity(&alias)?, before);
    assert_eq!(identity(&independently_opened)?, before);

    // Windows cap-std deliberately prevents rename while a directory handle is
    // held. Release all handles before the common close/rename/reopen control.
    // The directory itself is never deleted, excluding identifier reuse.
    drop(independently_opened);
    drop(alias);
    drop(held);
    fs::rename(&original, &destination)?;
    let held = Dir::open_ambient_dir(&destination, cap_std::ambient_authority())?;
    let alias = held.try_clone()?;
    let independently_opened = Dir::open_ambient_dir(&destination, cap_std::ambient_authority())?;
    fs::create_dir(&original)?;
    fs::create_dir(&copied)?;
    fs::copy(destination.join("keep"), copied.join("keep"))?;

    let reopened = Dir::open_ambient_dir(&destination, cap_std::ambient_authority())?;
    let replacement = Dir::open_ambient_dir(&original, cap_std::ambient_authority())?;
    let copy = Dir::open_ambient_dir(&copied, cap_std::ambient_authority())?;
    assert_eq!(identity(&held)?, before);
    assert_eq!(identity(&alias)?, before);
    assert_eq!(identity(&independently_opened)?, before);
    assert_eq!(identity(&reopened)?, before);
    assert_ne!(identity(&replacement)?, before);
    assert_ne!(identity(&copy)?, before);
    assert_ne!(identity(&copy)?, identity(&replacement)?);
    assert_eq!(held.read("keep")?, canary);
    assert_eq!(alias.read("keep")?, canary);
    assert_eq!(reopened.read("keep")?, canary);
    assert_eq!(copy.read("keep")?, canary);
    assert!(replacement.entries()?.next().is_none());
    Ok(())
}

#[cfg(unix)]
#[test]
fn unix_held_directory_identity_does_not_follow_a_replaced_path() -> Result<(), Box<dyn Error>> {
    let fixture = tempfile::tempdir()?;
    let original = fixture.path().join("original");
    let destination = fixture.path().join("moved");
    fs::create_dir(&original)?;
    fs::write(original.join("keep"), b"retained object\n")?;
    let held = Dir::open_ambient_dir(&original, cap_std::ambient_authority())?;
    let alias = held.try_clone()?;
    let before = identity(&held)?;

    fs::rename(&original, &destination)?;
    fs::create_dir(&original)?;
    let replacement = Dir::open_ambient_dir(&original, cap_std::ambient_authority())?;
    let reopened = Dir::open_ambient_dir(&destination, cap_std::ambient_authority())?;
    assert_eq!(identity(&held)?, before);
    assert_eq!(identity(&alias)?, before);
    assert_eq!(identity(&reopened)?, before);
    assert_ne!(identity(&replacement)?, before);
    assert_eq!(held.read("keep")?, b"retained object\n");
    assert!(replacement.entries()?.next().is_none());
    Ok(())
}

#[cfg(windows)]
#[test]
fn windows_directory_sharing_blocks_rename_until_the_last_handle_is_closed()
-> Result<(), Box<dyn Error>> {
    let fixture = tempfile::tempdir()?;
    let original = fixture.path().join("original");
    let destination = fixture.path().join("moved");
    fs::create_dir(&original)?;
    fs::write(original.join("keep"), b"retained object\n")?;
    let held = Dir::open_ambient_dir(&original, cap_std::ambient_authority())?;
    let alias = held.try_clone()?;
    let before = identity(&held)?;

    // cap-primitives4.0.3 omits FILE_SHARE_DELETE to protect its path lookups.
    // Preserve that policy; these are three distinct ownership-state controls.
    let refused = fs::rename(&original, &destination)
        .err()
        .ok_or("Windows directory rename did not refuse live handles")?;
    assert_eq!(refused.raw_os_error(), Some(32));
    drop(held);
    let refused = fs::rename(&original, &destination)
        .err()
        .ok_or("Windows directory rename did not refuse the retained clone")?;
    assert_eq!(refused.raw_os_error(), Some(32));
    assert_eq!(identity(&alias)?, before);
    assert_eq!(alias.read("keep")?, b"retained object\n");
    assert!(original.is_dir());
    assert!(!destination.exists());

    drop(alias);
    fs::rename(&original, &destination)?;
    let reopened = Dir::open_ambient_dir(&destination, cap_std::ambient_authority())?;
    assert_eq!(identity(&reopened)?, before);
    assert_eq!(reopened.read("keep")?, b"retained object\n");
    assert!(!original.exists());
    Ok(())
}
