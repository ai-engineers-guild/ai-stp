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
fn held_directory_identity_survives_rename_and_distinguishes_copies_and_replacements()
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

    // Every handle stays open, excluding identifier reuse after object deletion.
    // Changing which directory occupies the old pathname cannot retarget it.
    fs::rename(&original, &destination)?;
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
