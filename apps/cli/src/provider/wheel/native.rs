//! Header identity only; successful inspection never substitutes for execution evidence.

use super::invalid;
use crate::error::Result;

pub(super) fn validate(bytes: &[u8], platform: &str) -> Result<()> {
    let arm = platform.ends_with("/arm64");
    let valid = if platform.starts_with("linux/") {
        bytes.len() >= 64
            && bytes[..7] == *b"\x7fELF\x02\x01\x01"
            && matches!(u16::from_le_bytes([bytes[16], bytes[17]]), 2 | 3)
            && u16::from_le_bytes([bytes[18], bytes[19]]) == if arm { 183 } else { 62 }
    } else if platform.starts_with("macos/") {
        bytes.len() >= 32
            && bytes[..4] == [0xcf, 0xfa, 0xed, 0xfe]
            && bytes[4..8]
                == (if arm {
                    0x0100_000c_u32
                } else {
                    0x0100_0007_u32
                })
                .to_le_bytes()
            && bytes[12..16] == 2_u32.to_le_bytes()
    } else if platform.starts_with("windows/") && bytes.len() >= 64 && bytes[..2] == *b"MZ" {
        let offset = u32::from_le_bytes(bytes[60..64].try_into().map_err(|_| invalid())?) as usize;
        let header = offset
            .checked_add(26)
            .and_then(|end| bytes.get(offset..end));
        header.is_some_and(|header| {
            offset >= 64
                && header[..4] == *b"PE\0\0"
                && u16::from_le_bytes([header[4], header[5]]) == if arm { 0xaa64 } else { 0x8664 }
                && header[24..26] == 0x020b_u16.to_le_bytes()
        })
    } else {
        false
    };
    if valid { Ok(()) } else { Err(invalid()) }
}
