//! Durable UI choices, separate from the native engine's state and credentials.
use serde::{Deserialize, Serialize};
use std::fs::{self, OpenOptions};
use std::io::{self, Read, Write};
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Clone, Debug, Default, Deserialize, PartialEq, Serialize)]
#[cfg_attr(test, derive(ts_rs::TS))]
#[serde(deny_unknown_fields)]
pub struct UiPreferences {
    pub locale: Option<String>,
    pub theme: Option<String>,
}

impl UiPreferences {
    fn validate(&self) -> io::Result<()> {
        let configuration: serde_json::Value =
            serde_json::from_str(include_str!("../../src/localization.json"))
                .map_err(|_| io::Error::other("Packaged language configuration is invalid"))?;
        if self
            .locale
            .as_ref()
            .is_some_and(|locale| configuration["languages"].get(locale).is_none())
            || self
                .theme
                .as_deref()
                .is_some_and(|theme| !matches!(theme, "light" | "dark"))
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Unsupported UI preference",
            ));
        }
        Ok(())
    }

    pub fn read(directory: &Path) -> io::Result<Option<Self>> {
        let file = match fs::File::open(directory.join("preferences.json")) {
            Ok(file) => file,
            Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
            Err(error) => return Err(error),
        };
        let mut bytes = Vec::new();
        file.take(1025).read_to_end(&mut bytes)?;
        if bytes.len() > 1024 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "UI preferences exceed their size bound",
            ));
        }
        let preferences: Self = serde_json::from_slice(&bytes)?;
        preferences.validate()?;
        Ok(Some(preferences))
    }

    /// A successful reply follows file sync and atomic replacement, not a WebView flush timer.
    pub fn save(&self, directory: &Path) -> io::Result<()> {
        self.validate()?;
        fs::create_dir_all(directory)?;
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(io::Error::other)?
            .as_nanos();
        let temporary = directory.join(format!(
            ".preferences-{}-{nonce}.pending",
            std::process::id()
        ));
        let mut options = OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let result = (|| {
            let mut output = options.open(&temporary)?;
            serde_json::to_writer(&mut output, self)?;
            output.write_all(b"\n")?;
            output.sync_all()?;
            drop(output);
            fs::rename(&temporary, directory.join("preferences.json"))?;
            #[cfg(unix)]
            fs::File::open(directory)?.sync_all()?;
            Ok(())
        })();
        let _ = fs::remove_file(temporary);
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn acknowledged_choices_survive_a_fresh_read_and_replacement() {
        let directory = temporary_directory();
        assert_eq!(UiPreferences::read(&directory).unwrap(), None);
        let mut preferences = UiPreferences {
            locale: Some("ar".into()),
            theme: Some("dark".into()),
        };
        preferences.save(&directory).unwrap();
        assert_eq!(
            UiPreferences::read(&directory).unwrap(),
            Some(preferences.clone())
        );
        preferences.locale = Some("kk".into());
        preferences.save(&directory).unwrap();
        assert_eq!(UiPreferences::read(&directory).unwrap(), Some(preferences));
        assert_eq!(fs::read_dir(&directory).unwrap().count(), 1);
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn invalid_choices_cannot_replace_an_existing_preference() {
        let directory = temporary_directory();
        UiPreferences::default().save(&directory).unwrap();
        let original = fs::read(directory.join("preferences.json")).unwrap();
        let invalid = UiPreferences {
            locale: Some("../unknown".into()),
            theme: None,
        };
        assert!(invalid.save(&directory).is_err());
        assert_eq!(
            fs::read(directory.join("preferences.json")).unwrap(),
            original
        );
        fs::write(directory.join("preferences.json"), vec![b' '; 1025]).unwrap();
        assert!(UiPreferences::read(&directory).is_err());
        fs::remove_dir_all(directory).unwrap();
    }

    fn temporary_directory() -> std::path::PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path =
            std::env::temp_dir().join(format!("ai-stp-preferences-{}-{nonce}", std::process::id()));
        fs::create_dir(&path).unwrap();
        path
    }
}
