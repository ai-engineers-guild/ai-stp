use super::{Reader, context};
use serde_json::Value;

type Parsed<T> = std::result::Result<T, ()>;

pub(super) fn supported(name: &str) -> bool {
    matches!(
        name,
        "pyproject.toml"
            | "package.json"
            | "Cargo.toml"
            | "pubspec.yaml"
            | "Pipfile"
            | "setup.cfg"
            | "environment.yml"
            | "environment.yaml"
    ) || name.starts_with("requirements") && name.ends_with(".txt")
        || name == "test-requirements.txt"
}

pub(super) fn table(value: &Value) -> impl Iterator<Item = (&str, &Value)> {
    value
        .as_object()
        .into_iter()
        .flat_map(|v| v.iter())
        .map(|(k, v)| (k.as_str(), v))
}
pub(super) fn array(value: &Value) -> impl Iterator<Item = &Value> {
    value.as_array().into_iter().flatten()
}

pub(super) fn toml(text: &str) -> Parsed<Value> {
    fn scalar(value: &toml_edit::Value, depth: usize) -> Parsed<Value> {
        if depth > 64 {
            return Err(());
        }
        if let Some(table) = value.as_inline_table() {
            return table
                .iter()
                .map(|(k, v)| Ok((k.into(), scalar(v, depth + 1)?)))
                .collect::<Parsed<serde_json::Map<_, _>>>()
                .map(Value::Object);
        }
        if let Some(values) = value.as_array() {
            return values
                .iter()
                .map(|v| scalar(v, depth + 1))
                .collect::<Parsed<Vec<_>>>()
                .map(Value::Array);
        }
        Ok(if let Some(s) = value.as_str() {
            s.into()
        } else if let Some(n) = value.as_integer() {
            n.into()
        } else if let Some(b) = value.as_bool() {
            b.into()
        } else {
            Value::Null
        })
    }
    fn table(value: &toml_edit::Table, depth: usize) -> Parsed<Value> {
        value
            .iter()
            .map(|(k, v)| Ok((k.into(), item(v, depth + 1)?)))
            .collect::<Parsed<serde_json::Map<_, _>>>()
            .map(Value::Object)
    }
    fn item(value: &toml_edit::Item, depth: usize) -> Parsed<Value> {
        if depth > 64 {
            return Err(());
        }
        match value {
            toml_edit::Item::Table(value) => table(value, depth),
            toml_edit::Item::ArrayOfTables(values) => values
                .iter()
                .map(|v| table(v, depth + 1))
                .collect::<Parsed<Vec<_>>>()
                .map(Value::Array),
            toml_edit::Item::Value(value) => scalar(value, depth),
            toml_edit::Item::None => Ok(Value::Null),
        }
    }
    let document = text.parse::<toml_edit::DocumentMut>().map_err(|_| ())?;
    item(document.as_item(), 0)
}

pub(super) fn yaml(text: &str) -> Parsed<Value> {
    let value: Value = serde_saphyr::from_str_with_options(text, serde_saphyr::options! {
        duplicate_keys: serde_saphyr::DuplicateKeyPolicy::Error,
        reject_unsupported_tags: true,
        merge_keys: serde_saphyr::MergeKeyPolicy::AsOrdinary,
        budget: serde_saphyr::budget! { max_depth:64, max_events:50_000, max_aliases:0, max_documents:1 },
    }).map_err(|_|())?;
    fn merged(value: &Value) -> bool {
        match value {
            Value::Object(values) => values.contains_key("<<") || values.values().any(merged),
            Value::Array(values) => values.iter().any(merged),
            _ => false,
        }
    }
    if !value.is_object() || merged(&value) {
        return Err(());
    }
    Ok(value)
}

pub(super) fn read(name: &str, text: &str, b: &mut Reader) -> Parsed<()> {
    let alias = match name {
        "pyproject.toml" | "setup.cfg" => "python",
        "Pipfile" => "pipenv",
        "package.json" => "node",
        "Cargo.toml" => "rust",
        "pubspec.yaml" => "dart",
        "environment.yml" | "environment.yaml" => "conda",
        _ => "python",
    };
    b.add("alias", alias, "unspecified", None, "declared", "manifest");
    if name.ends_with(".txt") {
        b.requirements(
            text,
            if name.contains("test") {
                "testing"
            } else if name.contains("dev") {
                "development"
            } else {
                "production"
            },
            "requirements",
        );
        return Ok(());
    }
    if name == "setup.cfg" {
        let mut section = "";
        let mut active = None;
        for line in text.lines() {
            let trimmed = line.trim();
            if trimmed.starts_with('[') {
                section = trimmed;
                active = None;
                continue;
            }
            if line.starts_with(char::is_whitespace) {
                if let Some(context) = active {
                    b.requirements(trimmed, context, "setup.cfg");
                }
                continue;
            }
            if let Some((key, values)) = trimmed.split_once('=') {
                active = if section == "[options]" && key.trim() == "install_requires" {
                    Some("production")
                } else if section == "[options.extras_require]" {
                    Some(context(key.trim()))
                } else {
                    None
                };
                if let Some(context) = active {
                    b.requirements(values, context, "setup.cfg");
                }
            } else if !trimmed.is_empty() && !trimmed.starts_with(['#', ';']) {
                active = None;
            }
        }
        return Ok(());
    }
    let doc = if name == "package.json" {
        crate::wire::parse(text.as_bytes()).map_err(|_| ())?
    } else if name.ends_with(".yaml") || name.ends_with(".yml") {
        yaml(text)?
    } else {
        toml(text)?
    };
    if !doc.is_object() {
        return Err(());
    }
    let object_fields: &[&str] = match name {
        "pyproject.toml" => &["project", "tool", "dependency-groups", "build-system"],
        "Cargo.toml" => &[
            "package",
            "dependencies",
            "dev-dependencies",
            "build-dependencies",
            "workspace",
            "target",
        ],
        "package.json" => &[
            "dependencies",
            "optionalDependencies",
            "peerDependencies",
            "devDependencies",
            "engines",
        ],
        "pubspec.yaml" => &["dependencies", "dev_dependencies", "environment"],
        "Pipfile" => &["packages", "dev-packages", "requires"],
        _ => &[],
    };
    if object_fields
        .iter()
        .any(|key| doc.get(*key).is_some_and(|v| !v.is_object()))
    {
        return Err(());
    }
    if name == "pyproject.toml" {
        for value in [
            &doc["project"]["dependencies"],
            &doc["build-system"]["requires"],
        ] {
            if !value.is_null() && (!value.is_array() || array(value).any(|v| !v.is_string())) {
                return Err(());
            }
        }
        for values in [
            &doc["project"]["optional-dependencies"],
            &doc["dependency-groups"],
        ] {
            if !values.is_null()
                && (!values.is_object() || table(values).any(|(_, v)| !v.is_array()))
            {
                return Err(());
            }
        }
    }
    match name {
        "pyproject.toml" => python(&doc, b),
        "Cargo.toml" => cargo(&doc, b),
        "package.json" => {
            for (section, context) in [
                ("dependencies", "production"),
                ("optionalDependencies", "production"),
                ("peerDependencies", "production"),
                ("devDependencies", "development"),
            ] {
                for (name, spec) in table(&doc[section]) {
                    b.dependency(name, spec, context, section);
                }
            }
            for (name, spec) in table(&doc["engines"]) {
                b.add(
                    "alias",
                    name,
                    "unspecified",
                    spec.as_str(),
                    "declared",
                    "engines",
                );
            }
            if let Some((name, v)) = doc["packageManager"]
                .as_str()
                .and_then(|s| s.split_once('@'))
            {
                b.add(
                    "alias",
                    name,
                    "development",
                    Some(v),
                    "declared",
                    "packageManager",
                );
            }
        }
        "pubspec.yaml" => {
            for (section, context) in [
                ("dependencies", "production"),
                ("dev_dependencies", "testing"),
            ] {
                for (name, spec) in table(&doc[section]) {
                    b.dependency(name, spec, context, section);
                }
            }
            b.add(
                "alias",
                "dart",
                "unspecified",
                doc["environment"]["sdk"].as_str(),
                "declared",
                "environment.sdk",
            );
        }
        "Pipfile" => {
            for (section, context) in [("packages", "production"), ("dev-packages", "development")]
            {
                for (name, spec) in table(&doc[section]) {
                    b.dependency(&name.to_lowercase(), spec, context, section);
                }
            }
            for key in ["python_version", "python_full_version"] {
                if let Some(v) = doc["requires"][key].as_str() {
                    b.add("alias", "python", "unspecified", Some(v), "declared", key);
                }
            }
        }
        "environment.yml" | "environment.yaml" => {
            for dep in array(&doc["dependencies"]) {
                if let Some(line) = dep.as_str() {
                    let line = line.rsplit("::").next().unwrap_or(line);
                    let end = line.find(['=', '<', '>', '!']).unwrap_or(line.len());
                    b.add(
                        "package",
                        &line[..end],
                        "production",
                        Some(&line[end..]),
                        "declared",
                        "dependencies",
                    );
                } else {
                    for line in array(&dep["pip"]).filter_map(Value::as_str) {
                        b.requirements(line, "production", "pip");
                    }
                }
            }
        }
        _ => return Err(()),
    }
    Ok(())
}

fn python(doc: &Value, b: &mut Reader) {
    if let Some(v) = doc["project"]["requires-python"].as_str() {
        b.add(
            "alias",
            "python",
            "unspecified",
            Some(v),
            "declared",
            "project.requires-python",
        );
    }
    for (section, values, ctx) in [
        (
            "project.dependencies",
            &doc["project"]["dependencies"],
            "production",
        ),
        (
            "build-system.requires",
            &doc["build-system"]["requires"],
            "development",
        ),
    ] {
        for line in array(values).filter_map(Value::as_str) {
            b.requirements(line, ctx, section);
        }
    }
    for (section, groups) in [
        (
            "optional-dependencies",
            &doc["project"]["optional-dependencies"],
        ),
        ("dependency-groups", &doc["dependency-groups"]),
    ] {
        for (group, values) in table(groups) {
            for value in array(values) {
                if let Some(line) = value.as_str() {
                    b.requirements(line, context(group), section);
                } else if value.get("include-group").is_none() {
                    b.stopped.get_or_insert("unsupported dependency group");
                }
            }
        }
    }
    // Group inclusion is not evaluated; every directly declared group is scanned.
    let poetry = &doc["tool"]["poetry"];
    for (section, ctx) in [
        ("dependencies", "production"),
        ("dev-dependencies", "development"),
    ] {
        for (name, spec) in table(&poetry[section]) {
            if name == "python" {
                b.add(
                    "alias",
                    "python",
                    "unspecified",
                    spec.as_str(),
                    "declared",
                    "tool.poetry.dependencies",
                );
            } else {
                b.dependency(name, spec, ctx, "tool.poetry");
            }
        }
    }
    for (group, body) in table(&poetry["group"]) {
        for (name, spec) in table(&body["dependencies"]) {
            b.dependency(name, spec, context(group), "tool.poetry.group");
        }
    }
}

fn cargo(doc: &Value, b: &mut Reader) {
    for (body, workspace) in std::iter::once((doc, false))
        .chain(std::iter::once((&doc["workspace"], true)))
        .chain(table(&doc["target"]).map(|(_, v)| (v, false)))
    {
        for (section, ctx) in [
            ("dependencies", "production"),
            ("dev-dependencies", "testing"),
            ("build-dependencies", "development"),
        ] {
            for (name, spec) in table(&body[section]) {
                b.dependency(
                    name,
                    spec,
                    if workspace { "unspecified" } else { ctx },
                    if workspace {
                        "workspace.dependencies"
                    } else {
                        section
                    },
                );
            }
        }
    }
    if let Some(v) = doc["package"]["rust-version"].as_str() {
        b.add(
            "alias",
            "rust",
            "unspecified",
            Some(v),
            "declared",
            "package.rust-version",
        );
    }
}
