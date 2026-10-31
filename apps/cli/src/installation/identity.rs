//! Complete held-object identities, including all 128 Windows file-ID bits.

use cap_std::fs::{Dir, File};
use std::io;

// A byte representation is Copy/Hash and lossless in persisted JSON. Native
// integer IDs must not pass through JavaScript's 53-bit numeric representation.
pub(super) type Identity = [u8; 25];

fn plain(metadata: &cap_std::fs::Metadata, directory: bool) -> io::Result<()> {
    use cap_fs_ext::MetadataExt;
    if metadata.is_symlink()
        || metadata.is_dir() != directory
        || (!directory && (!metadata.is_file() || metadata.nlink() != 1))
    {
        return Err(io::Error::other("installation object is not plain"));
    }
    #[cfg(windows)]
    {
        use cap_std::fs::MetadataExt;
        if metadata.file_attributes() & 0x400 != 0 {
            return Err(io::Error::other("installation object is a reparse point"));
        }
    }
    Ok(())
}

fn encode(kind: u8, volume: u64, file: u128) -> Identity {
    let mut value = [0; 25];
    value[0] = kind;
    value[1..9].copy_from_slice(&volume.to_le_bytes());
    value[9..].copy_from_slice(&file.to_le_bytes());
    value
}

pub(super) fn directory(directory: &Dir) -> io::Result<Identity> {
    let metadata = directory.dir_metadata()?;
    plain(&metadata, true)?;
    #[cfg(unix)]
    {
        use cap_fs_ext::MetadataExt;
        Ok(encode(1, metadata.dev(), u128::from(metadata.ino())))
    }
    #[cfg(windows)]
    {
        windows(directory)
    }
    #[cfg(not(any(unix, windows)))]
    {
        let _ = directory;
        Err(io::Error::other("physical object identity is unavailable"))
    }
}

pub(super) fn file(file: &File) -> io::Result<Identity> {
    let metadata = file.metadata()?;
    plain(&metadata, false)?;
    #[cfg(unix)]
    {
        use cap_fs_ext::MetadataExt;
        Ok(encode(1, metadata.dev(), u128::from(metadata.ino())))
    }
    #[cfg(windows)]
    {
        windows(file)
    }
    #[cfg(not(any(unix, windows)))]
    {
        let _ = file;
        Err(io::Error::other("physical object identity is unavailable"))
    }
}

pub(super) fn standard_file(file: &std::fs::File) -> io::Result<Identity> {
    let metadata = cap_std::fs::Metadata::from_file(file)?;
    plain(&metadata, false)?;
    #[cfg(unix)]
    {
        use cap_fs_ext::MetadataExt;
        Ok(encode(1, metadata.dev(), u128::from(metadata.ino())))
    }
    #[cfg(windows)]
    {
        windows(file)
    }
    #[cfg(not(any(unix, windows)))]
    {
        let _ = file;
        Err(io::Error::other("physical object identity is unavailable"))
    }
}

#[cfg(windows)]
fn windows(file: &impl fs_id::GetID) -> io::Result<Identity> {
    let identity = fs_id::FileID::new(file).map_err(io::Error::other)?;
    Ok(encode(
        2,
        identity.storage_id(),
        identity.internal_file_id(),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn all_identifier_bits_and_platform_survive_a_json_round_trip()
    -> Result<(), Box<dyn std::error::Error>> {
        let first = encode(2, u64::MAX, u128::MAX);
        let different_high_bits = encode(2, u64::MAX, u128::from(u64::MAX));
        assert_ne!(first, different_high_bits);
        assert_ne!(encode(1, 7, 9), encode(2, 7, 9));
        assert_eq!(
            serde_json::from_slice::<Identity>(&serde_json::to_vec(&first)?)?,
            first
        );
        Ok(())
    }
}
