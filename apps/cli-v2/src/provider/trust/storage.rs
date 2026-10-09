//! One leased canonical state file; every authenticated step is durably acknowledged.

use std::path::Path;

use super::{State, invalid};
use crate::{error::Result, files::OwnedDirectory, wire};

const MAX_STATE: usize = 16 * 1024 * 1024;
const OWNER: &[u8] = b"ai-stp-cli-v2:sigstore-tuf/v1\n";

pub(super) struct Storage(OwnedDirectory);

impl Storage {
    pub(super) fn open(parent: &Path) -> Result<(Self, State)> {
        let owned =
            OwnedDirectory::open(parent, "sigstore-tuf", OWNER, true)?.ok_or_else(invalid)?;
        let initialized = owned.read_file("initialized", 2)?;
        if initialized.as_deref().is_some_and(|value| value != b"1\n") {
            return Err(invalid());
        }
        let state = match owned.read_file("state.json", MAX_STATE as u64)? {
            Some(bytes) => serde_json::from_value(wire::parse(&bytes)?).map_err(|_| invalid())?,
            None if initialized.is_none() => State::default(),
            None => return Err(invalid()),
        };
        Ok((Self(owned), state))
    }

    pub(super) fn save(&self, state: &State) -> Result<()> {
        let bytes = serde_json::to_vec(state).map_err(|_| invalid())?;
        if bytes.len() > MAX_STATE {
            return Err(invalid());
        }
        self.0.atomic("state.json", &bytes)?;
        self.0.atomic("initialized", b"1\n")
    }
}
