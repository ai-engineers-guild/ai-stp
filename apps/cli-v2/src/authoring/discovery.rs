//! Bounded inspection of declared native layouts at one explicit scope root.

use std::{
    collections::BTreeSet,
    io::Read,
    path::{Path, PathBuf},
    time::{Duration, Instant},
};

use cap_fs_ext::DirExt;
use cap_std::fs::{Dir, DirEntry, Metadata};
use serde::Serialize;
use serde_json::{Value, json};

use super::contribution::{self, Format};
use crate::{
    artifacts, digest,
    error::{ErrorKind, Failure, Result},
    files,
    harnesses::{self, Definition, Layout, Root, Scope, Shape},
    projects,
};

#[derive(Serialize)]
pub struct Candidate {
    pub component_type: String,
    pub projection_kind: String,
    pub native_role: Option<&'static str>,
    pub harness_id: String,
    pub scope: Scope,
    pub candidate_id: String,
    pub layout_source: String,
    pub provenance: Value,
    pub source_path: String,
    pub native_path: String,
    pub byte_length: Option<u64>,
    pub holds_secret: bool,
    pub reason: &'static str,
    pub entry_points: Vec<String>,
    pub transport_capabilities: Vec<String>,
    pub evidence_refs: Vec<String>,
    pub declared_key: String,
    #[serde(skip)]
    pub absolute: PathBuf,
}

#[derive(Serialize)]
pub struct Diagnostic {
    pub code: &'static str,
    pub source: String,
    pub reason: &'static str,
}

#[derive(Serialize)]
pub struct Discovery {
    pub components: Vec<Candidate>,
    pub diagnostics: Vec<Diagnostic>,
    pub complete: bool,
}

fn refused() -> Failure {
    Failure::precondition("the declared layout is unsafe, unreadable or exceeds its limits")
}

fn absent(error: &std::io::Error) -> bool {
    matches!(
        error.kind(),
        std::io::ErrorKind::NotFound | std::io::ErrorKind::NotADirectory
    )
}

fn plain(metadata: &Metadata) -> bool {
    if metadata.file_type().is_symlink() || (!metadata.is_file() && !metadata.is_dir()) {
        return false;
    }
    #[cfg(windows)]
    {
        use cap_std::fs::MetadataExt;
        if metadata.file_attributes() & 0x400 != 0 {
            return false;
        }
    }
    !metadata.is_file() || cap_fs_ext::MetadataExt::nlink(metadata) == 1
}

fn offered(name: &str) -> bool {
    name != "index.json"
        && !name.ends_with('~')
        && !name.split('.').skip(1).any(|part| {
            ["bak", "orig"]
                .iter()
                .any(|suffix| part == *suffix || part.starts_with(&format!("{suffix}-")))
        })
}

struct Scanner {
    started: Instant,
    entries: usize,
}

impl Scanner {
    fn check(&self) -> Result<()> {
        if self.entries > 4000 || self.started.elapsed() > Duration::from_secs(10) {
            return Err(refused());
        }
        Ok(())
    }

    fn list(&mut self, directory: &Dir) -> Result<Vec<DirEntry>> {
        let mut entries = Vec::new();
        for entry in directory.entries().map_err(|_| refused())? {
            self.entries += 1;
            self.check()?;
            if entries.len() >= 1000 {
                return Err(refused());
            }
            entries.push(entry.map_err(|_| refused())?);
        }
        entries.sort_by_key(DirEntry::file_name);
        Ok(entries)
    }

    fn parent(&self, directory: &Dir, relative: &str) -> Result<Option<(Dir, String)>> {
        self.check()?;
        if !artifacts::safe_path(relative) {
            return Err(refused());
        }
        let mut current = directory.try_clone().map_err(|_| refused())?;
        let mut parts = relative.split('/').peekable();
        while let Some(part) = parts.next() {
            if parts.peek().is_none() {
                return Ok(Some((current, part.into())));
            }
            let Some(metadata) = self.metadata(&current, part)? else {
                return Ok(None);
            };
            if !metadata.is_dir() {
                return Ok(None);
            }
            current = current.open_dir_nofollow(part).map_err(|_| refused())?;
        }
        Err(refused())
    }

    fn metadata(&self, directory: &Dir, name: &str) -> Result<Option<Metadata>> {
        self.check()?;
        match directory.symlink_metadata(name) {
            Ok(metadata) if plain(&metadata) => Ok(Some(metadata)),
            Ok(_) => Err(refused()),
            Err(error) if absent(&error) => Ok(None),
            Err(_) => Err(refused()),
        }
    }

    fn plugin_manifest(&mut self, directory: &Dir) -> Result<bool> {
        if self
            .metadata(directory, "plugin.json")?
            .is_some_and(|meta| meta.is_file())
        {
            return Ok(true);
        }
        for entry in self.list(directory)? {
            let name = entry.file_name().into_string().map_err(|_| refused())?;
            if !name.starts_with('.') || !name.ends_with("-plugin") {
                continue;
            }
            if self
                .metadata(directory, &name)?
                .is_some_and(|meta| meta.is_dir())
            {
                let child = directory.open_dir_nofollow(&name).map_err(|_| refused())?;
                if self
                    .metadata(&child, "plugin.json")?
                    .is_some_and(|meta| meta.is_file())
                {
                    return Ok(true);
                }
            }
        }
        Ok(false)
    }

    fn declared(&self, directory: &Dir, name: &str, layout: &Layout) -> Result<Vec<String>> {
        if layout.declared_key.is_empty() {
            return Ok(Vec::new());
        }
        if projects::secret_name(name) {
            return Err(refused());
        }
        let mut file = files::open_regular(directory, Path::new(name)).map_err(|_| refused())?;
        let before = file.metadata().map_err(|_| refused())?;
        if !plain(&before) || before.len() > 1024 * 1024 {
            return Err(refused());
        }
        let mut bytes = Vec::new();
        file.by_ref()
            .take(1024 * 1024 + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| refused())?;
        let after = file.metadata().map_err(|_| refused())?;
        if !plain(&after)
            || bytes.len() as u64 != before.len()
            || before.len() != after.len()
            || before.modified().map_err(|_| refused())?
                != after.modified().map_err(|_| refused())?
        {
            return Err(refused());
        }
        contribution::entry_names(Format::for_path(name)?, &bytes, &layout.declared_key)
    }

    fn layout(
        &mut self,
        directory: &Dir,
        root: &Path,
        harness: &Definition,
        layout: &Layout,
    ) -> Result<Vec<Candidate>> {
        let Some((parent, name)) = self.parent(directory, &layout.relative)? else {
            return Ok(Vec::new());
        };
        let Some(metadata) = self.metadata(&parent, &name)? else {
            return Ok(Vec::new());
        };
        match layout.shape {
            Shape::File if metadata.is_file() => {
                let names = self.declared(&parent, &name, layout)?;
                if !layout.declared_key.is_empty() && names.is_empty() {
                    return Ok(Vec::new());
                }
                let evidence = names
                    .into_iter()
                    .map(|name| format!("{}.{name}", layout.declared_key))
                    .collect();
                Ok(vec![describe(
                    root,
                    &layout.relative,
                    &metadata,
                    harness,
                    layout,
                    evidence,
                )?])
            }
            Shape::Directory if metadata.is_dir() => {
                let children = parent.open_dir_nofollow(&name).map_err(|_| refused())?;
                let mut found = Vec::new();
                for entry in self.list(&children)? {
                    let name = entry.file_name().into_string().map_err(|_| refused())?;
                    if !offered(&name) || layout.excluded_names.contains(&name) {
                        continue;
                    }
                    let relative = format!("{}/{name}", layout.relative);
                    if !artifacts::safe_path(&relative) {
                        return Err(refused());
                    }
                    let metadata = self.metadata(&children, &name)?.ok_or_else(refused)?;
                    if layout.excludes_plugin_manifest && metadata.is_dir() {
                        let child = children.open_dir_nofollow(&name).map_err(|_| refused())?;
                        if self.plugin_manifest(&child)? {
                            continue;
                        }
                    }
                    found.push(describe(
                        root,
                        &relative,
                        &metadata,
                        harness,
                        layout,
                        Vec::new(),
                    )?);
                }
                Ok(found)
            }
            _ => Ok(Vec::new()),
        }
    }
}

fn describe(
    root: &Path,
    relative: &str,
    metadata: &Metadata,
    harness: &Definition,
    layout: &Layout,
    evidence_refs: Vec<String>,
) -> Result<Candidate> {
    let absolute = root.join(relative);
    let source_path = files::display(Path::new(&files::location(&absolute)?));
    let native_role = (layout.component_type == "mcp").then_some("mcp_client_config");
    let holds_secret = relative.split('/').any(projects::secret_name);
    let provenance = json!({"kind":"filesystem", "state":"local", "repository":null,
        "revision":null, "subpath":null, "package_name":null, "package_version":null, "digest":null});
    let candidate_id = digest::canonical(
        "ai-stp:native-discovery:v1",
        &json!({
            "component_type":layout.component_type, "projection_kind":layout.projection_kind,
            "native_role":native_role, "harness_id":harness.harness_id, "layout_source":layout.source,
            "scope":layout.scope, "source_path":source_path, "provenance":provenance,
            "entry_points":[], "transport_capabilities":[], "evidence_refs":evidence_refs
        }),
    )?;
    let mut provenance = provenance;
    provenance["evidence"] = json!([format!("layout:{}", layout.source)]);
    Ok(Candidate {
        component_type: layout.component_type.clone(),
        projection_kind: layout.projection_kind.clone(),
        native_role,
        harness_id: harness.harness_id.clone(),
        scope: layout.scope,
        candidate_id,
        layout_source: layout.source.clone(),
        provenance,
        source_path,
        native_path: relative.into(),
        byte_length: metadata.is_file().then_some(metadata.len()),
        holds_secret,
        reason: if holds_secret {
            "named as a credential file; its content is never read"
        } else {
            "found where this harness declares this kind lives"
        },
        entry_points: Vec::new(),
        transport_capabilities: Vec::new(),
        evidence_refs,
        declared_key: layout.declared_key.clone(),
        absolute,
    })
}

/// Completeness refers only to matching catalog layouts at this explicit root.
/// Package provenance, portable recursion and installed-plugin adapters are separate sources.
pub fn at(root: &Path, harness: &str, scope: Scope, root_kind: Root) -> Result<Discovery> {
    let definition = harnesses::definition(harness)?;
    let mut layouts: Vec<_> = definition
        .layouts
        .iter()
        .filter(|layout| layout.scope == scope && layout.root == root_kind)
        .map(|layout| (definition, layout))
        .collect();
    if harness != "undefined" {
        let shared = harnesses::definition("undefined")?;
        for layout in shared.layouts.iter().filter(|layout| {
            layout.scope == scope && layout.root == root_kind && layout.component_type == "skill"
        }) {
            if !layouts.iter().any(|(_, own)| {
                own.relative == layout.relative && own.component_type == layout.component_type
            }) {
                layouts.push((shared, layout));
            }
        }
    }
    if layouts.is_empty() {
        return Err(Failure::input(
            "the harness has no declared layouts for this scope and root",
        ));
    }
    let metadata = root
        .symlink_metadata()
        .map_err(|_| Failure::new(ErrorKind::NotFound, "discovery root is unavailable"))?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() {
        return Err(Failure::input("discovery requires a real directory"));
    }
    let root = root.canonicalize().map_err(|_| refused())?;
    if root.parent().is_none()
        || (scope == Scope::Project
            && files::home()
                .and_then(|home| home.canonicalize().ok())
                .is_some_and(|home| home == root))
    {
        return Err(Failure::input("the selected discovery root is too broad"));
    }
    let directory =
        Dir::open_ambient_dir(&root, cap_std::ambient_authority()).map_err(|_| refused())?;
    let mut scanner = Scanner {
        started: Instant::now(),
        entries: 0,
    };
    let mut result = Discovery {
        components: Vec::new(),
        diagnostics: Vec::new(),
        complete: true,
    };
    let mut seen = BTreeSet::new();
    for (definition, layout) in layouts {
        match scanner.layout(&directory, &root, definition, layout) {
            Ok(found) => result.components.extend(
                found
                    .into_iter()
                    .filter(|item| seen.insert(item.candidate_id.clone())),
            ),
            Err(_) => {
                result.complete = false;
                result.diagnostics.push(Diagnostic { code:"incomplete_layout", source:layout.relative.clone(), reason:"layout contains unsafe or unreadable entries, invalid configuration, or exceeds its budget" });
            }
        }
    }
    result.components.sort_by(|a, b| {
        (&a.harness_id, &a.component_type, &a.native_path).cmp(&(
            &b.harness_id,
            &b.component_type,
            &b.native_path,
        ))
    });
    Ok(result)
}
