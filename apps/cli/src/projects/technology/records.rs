use super::{
    Reader,
    manifests::{array, table, toml, yaml},
};
use serde_json::Value;
use std::collections::BTreeSet;

type Parsed<T> = std::result::Result<T, ()>;

pub(super) fn supported(name: &str) -> bool {
    matches!(
        name,
        "uv.lock"
            | "poetry.lock"
            | "Cargo.lock"
            | "package-lock.json"
            | "pubspec.lock"
            | "pnpm-lock.yaml"
            | "yarn.lock"
            | "go.mod"
            | "go.sum"
            | "Dockerfile"
            | "Containerfile"
            | ".gitlab-ci.yml"
            | ".gitlab-ci.yaml"
            | ".python-version"
            | ".node-version"
            | ".nvmrc"
            | ".ruby-version"
            | ".java-version"
            | ".go-version"
            | "runtime.txt"
            | ".tool-versions"
            | "mise.toml"
            | ".mise.toml"
    ) || name.starts_with("Dockerfile.")
        || name.starts_with("Containerfile.")
        || name.ends_with(".dockerfile")
        || (name.starts_with("compose.") || name.starts_with("docker-compose."))
            && (name.ends_with(".yml") || name.ends_with(".yaml"))
}

pub(super) fn read(name: &str, text: &str, b: &mut Reader) -> Parsed<()> {
    match name {
        "uv.lock" | "poetry.lock" | "Cargo.lock" => {
            let doc = toml(text)?;
            let alias = match name {
                "uv.lock" => "uv",
                "poetry.lock" => "poetry",
                _ => "cargo",
            };
            b.add(
                "alias",
                alias,
                "development",
                None,
                "configuration",
                "lockfile",
            );
            for row in array(&doc["package"]) {
                if let Some(name) = row["name"].as_str() {
                    b.add(
                        "package",
                        name,
                        "unspecified",
                        row["version"].as_str(),
                        "lock_file",
                        "package",
                    );
                }
            }
        }
        "package-lock.json" => {
            let doc = crate::wire::parse(text.as_bytes()).map_err(|_| ())?;
            b.add(
                "alias",
                "npm",
                "development",
                None,
                "configuration",
                "lockfile",
            );
            if doc["lockfileVersion"] != 2 && doc["lockfileVersion"] != 3 {
                b.stopped.get_or_insert("unsupported npm lockfile version");
                return Ok(());
            }
            for (path, row) in table(&doc["packages"]) {
                if let Some((_, name)) = path.rsplit_once("node_modules/") {
                    b.add(
                        "package",
                        name,
                        "unspecified",
                        row["version"].as_str(),
                        "lock_file",
                        "packages",
                    );
                }
            }
        }
        "pubspec.lock" => {
            let doc = yaml(text)?;
            for (name, row) in table(&doc["packages"]) {
                b.add(
                    "package",
                    name,
                    "unspecified",
                    row["version"].as_str(),
                    "lock_file",
                    "packages",
                );
            }
        }
        "pnpm-lock.yaml" => {
            let doc = yaml(text)?;
            b.add(
                "alias",
                "pnpm",
                "development",
                None,
                "configuration",
                "lockfile",
            );
            for (key, _) in table(&doc["packages"]) {
                let key = key.trim_start_matches('/').split('(').next().unwrap_or(key);
                // pnpm 6/9 identities use name@version; older slash identities
                // are retained only when the final segment starts with a digit.
                let pair = key
                    .rsplit_once('@')
                    .filter(|(name, _)| !name.is_empty())
                    .or_else(|| {
                        key.rsplit_once('/')
                            .filter(|(_, v)| v.starts_with(|c: char| c.is_ascii_digit()))
                    });
                if let Some((name, v)) = pair {
                    b.add(
                        "package",
                        name,
                        "unspecified",
                        Some(v),
                        "lock_file",
                        "packages",
                    );
                } else {
                    b.stopped.get_or_insert("unsupported pnpm package identity");
                }
            }
        }
        "yarn.lock" => {
            if text.starts_with("# yarn lockfile v1") || text.contains("# yarn lockfile v1\n") {
                b.stopped.get_or_insert("unsupported Yarn classic lockfile");
                return Ok(());
            }
            let doc = yaml(text)?;
            for (key, row) in table(&doc) {
                if key == "__metadata" {
                    continue;
                }
                for locator in key.split(", ") {
                    if let Some((name, _)) = locator.rsplit_once('@') {
                        b.add(
                            "package",
                            name,
                            "unspecified",
                            row["version"].as_str(),
                            "lock_file",
                            "resolution",
                        );
                    }
                }
            }
        }
        "go.mod" | "go.sum" => go(name, text, b),
        "mise.toml" | ".mise.toml" => {
            let doc = toml(text)?;
            for (name, spec) in table(&doc["tools"]) {
                if let Some(v) = spec.as_str().or_else(|| spec["version"].as_str()) {
                    b.add(
                        "alias",
                        name,
                        "unspecified",
                        Some(v),
                        "configuration",
                        "tools",
                    );
                }
                for v in array(spec).filter_map(Value::as_str) {
                    b.add(
                        "alias",
                        name,
                        "unspecified",
                        Some(v),
                        "configuration",
                        "tools",
                    );
                }
            }
        }
        ".tool-versions" => {
            for line in text.lines() {
                let mut words = line.split('#').next().unwrap_or("").split_whitespace();
                if let Some(name) = words.next() {
                    for v in words {
                        b.add(
                            "alias",
                            name,
                            "unspecified",
                            Some(v),
                            "configuration",
                            "tools",
                        );
                    }
                }
            }
        }
        ".python-version" | ".node-version" | ".nvmrc" | ".ruby-version" | ".java-version"
        | ".go-version" | "runtime.txt" => {
            let alias = match name {
                ".node-version" | ".nvmrc" => "node",
                ".ruby-version" => "ruby",
                ".java-version" => "java",
                ".go-version" => "go",
                _ => "python",
            };
            for line in text.lines() {
                let line = line.split('#').next().unwrap_or("").trim();
                let line = if name == "runtime.txt" {
                    line.strip_prefix("python-").unwrap_or(line)
                } else {
                    line
                };
                if !line.is_empty() {
                    b.add(
                        "alias",
                        alias,
                        "unspecified",
                        Some(line),
                        "configuration",
                        "runtime",
                    );
                }
            }
        }
        ".gitlab-ci.yml" | ".gitlab-ci.yaml" => {
            let doc = yaml(text)?;
            for (_, job) in std::iter::once(("", &doc)).chain(table(&doc)) {
                image_value(&job["image"], "testing", b);
                for service in array(&job["services"]) {
                    image_value(service, "testing", b);
                }
            }
            if doc.get("include").is_some() {
                b.stopped
                    .get_or_insert("external CI configuration is not resolved");
            }
        }
        name if name.ends_with(".yml") || name.ends_with(".yaml") => {
            let doc = yaml(text)?;
            for (_, service) in table(&doc["services"]) {
                image_value(&service["image"], "production", b);
            }
            if doc.get("include").is_some() {
                b.stopped
                    .get_or_insert("external Compose configuration is not resolved");
            }
        }
        _ => docker(text, b),
    }
    Ok(())
}

fn image_value(value: &Value, context: &str, b: &mut Reader) {
    if let Some(value) = value.as_str().or_else(|| value["name"].as_str()) {
        image(value, context, b);
    }
}
fn image(reference: &str, context: &str, b: &mut Reader) {
    if reference.contains(['$', '{', '}']) {
        b.stopped.get_or_insert("dynamic image reference");
        return;
    }
    let (name, digest) = reference
        .split_once('@')
        .map_or((reference, None), |(n, d)| (n, Some(d)));
    if digest.is_some_and(|value| {
        !value
            .strip_prefix("sha256:")
            .is_some_and(|hash| hash.len() == 64 && hash.bytes().all(|b| b.is_ascii_hexdigit()))
    }) {
        b.stopped
            .get_or_insert("invalid image digest or credentials");
        return;
    }
    let (name, tag) = name
        .rsplit_once(':')
        .filter(|(_, v)| !v.contains('/'))
        .map_or((name, None), |(n, v)| (n, Some(v)));
    let name = name
        .strip_prefix("docker.io/")
        .unwrap_or(name)
        .strip_prefix("library/")
        .unwrap_or(name.strip_prefix("docker.io/").unwrap_or(name));
    if name == "scratch" {
        return;
    }
    // A digest is not a release version. Only the coordinate and a safe tag leave.
    b.add(
        "image",
        name,
        context,
        if digest.is_some() { None } else { tag },
        "configuration",
        "image",
    );
}
fn docker(text: &str, b: &mut Reader) {
    let mut stages = BTreeSet::new();
    for line in text.lines() {
        let words: Vec<_> = line.split_whitespace().collect();
        if words
            .first()
            .is_none_or(|v| !v.eq_ignore_ascii_case("FROM"))
        {
            continue;
        }
        if line.trim_end().ends_with('\\') {
            b.stopped
                .get_or_insert("continued Docker FROM is not resolved");
            continue;
        }
        let mut iter = words.iter().skip(1).filter(|v| !v.starts_with("--"));
        if let Some(value) = iter.next()
            && !stages.contains(&value.to_ascii_lowercase())
        {
            image(value, "production", b);
        }
        if iter.next().is_some_and(|v| v.eq_ignore_ascii_case("AS"))
            && let Some(alias) = iter.next()
        {
            stages.insert(alias.to_ascii_lowercase());
        }
    }
}
fn go(name: &str, text: &str, b: &mut Reader) {
    b.add("alias", "go", "unspecified", None, "declared", name);
    let mut block = "";
    for line in text.lines() {
        let line = line.split("//").next().unwrap_or("").trim();
        let words: Vec<_> = line.split_whitespace().collect();
        if name == "go.sum" {
            if words.len() == 3 {
                b.add(
                    "package",
                    words[0],
                    "unspecified",
                    Some(words[1].trim_end_matches("/go.mod")),
                    "checksum_file",
                    "go.sum",
                );
            }
            continue;
        }
        if words.len() == 2 && words[1] == "(" {
            block = words[0];
            continue;
        }
        if line == ")" {
            block = "";
            continue;
        }
        match words.as_slice() {
            ["go", version] => b.add(
                "alias",
                "go",
                "unspecified",
                Some(version),
                "declared",
                "go",
            ),
            ["require", name, version] => b.add(
                "package",
                name,
                "production",
                Some(version),
                "declared",
                "require",
            ),
            [name, version] if block == "require" => b.add(
                "package",
                name,
                "production",
                Some(version),
                "declared",
                "require",
            ),
            _ => {}
        }
    }
}
