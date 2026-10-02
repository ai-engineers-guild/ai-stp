//! Command construction from `help --agent --json` descriptors.
//!
//! The app never invents flags: argv is assembled from the declared
//! `parameters` of a `CommandDescriptor`, honoring `parameter_rules`.
//! Undeclared options are refused up front.

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CommandParameter {
    pub name: String,
    pub kind: String, // "option" | "argument"
    #[serde(default)]
    pub value_type: String, // "string" | "boolean" | "integer"
    #[serde(default)]
    pub required: bool,
    #[serde(default)]
    pub repeatable: bool,
    #[serde(default)]
    pub choices: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParameterRule {
    pub kind: String, // exactly_one | at_most_one | required_when | forbidden_when
    #[serde(default)]
    pub parameters: Vec<String>,
    /// Empty string means unconditional (the wire default is "").
    #[serde(default)]
    pub when_parameter: String,
    /// May carry the sentinel "present" (parameter is set to any value).
    #[serde(default)]
    pub when_values: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CommandDescriptor {
    /// Command words, e.g. `["install", "plan"]`. The wire form is a list;
    /// callers address commands by the space-joined path.
    pub path: Vec<String>,
    #[serde(default)]
    pub summary: String,
    #[serde(default)]
    pub mutability: String, // read | plan | apply | destructive
    #[serde(default)]
    pub confirmation: String, // none | explicit_flag | plan_digest
    #[serde(default)]
    pub parameters: Vec<CommandParameter>,
    #[serde(default)]
    pub parameter_rules: Vec<ParameterRule>,
    #[serde(default)]
    pub result_schema: Option<String>,
}

impl CommandDescriptor {
    pub fn path_key(&self) -> String {
        self.path.join(" ")
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MachineHelp {
    pub cli_version: String,
    pub registry_digest: String,
    #[serde(default)]
    pub commands: Vec<CommandDescriptor>,
}

#[derive(Debug)]
pub enum BuildError {
    UnknownCommand(String),
    UnknownParameter(String),
    MissingRequired(Vec<String>),
    RuleViolation(String),
    ChoiceViolation { name: String, value: String },
}

impl std::fmt::Display for BuildError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::UnknownCommand(p) => write!(f, "unknown command path: {p}"),
            Self::UnknownParameter(n) => write!(f, "parameter not declared: {n}"),
            Self::MissingRequired(ps) => write!(f, "missing required: {}", ps.join(", ")),
            Self::RuleViolation(r) => write!(f, "parameter rule violated: {r}"),
            Self::ChoiceViolation { name, value } => {
                write!(f, "value {value} not in choices for {name}")
            }
        }
    }
}

impl std::error::Error for BuildError {}

#[derive(Clone)]
pub struct CommandRegistry {
    by_path: HashMap<String, CommandDescriptor>,
    pub registry_digest: String,
}

impl CommandRegistry {
    pub fn from_help(help: &MachineHelp) -> Self {
        Self {
            by_path: help
                .commands
                .iter()
                .map(|c| (c.path_key(), c.clone()))
                .collect(),
            registry_digest: help.registry_digest.clone(),
        }
    }

    pub fn descriptor(&self, path: &str) -> Option<&CommandDescriptor> {
        self.by_path.get(path)
    }

    /// All descriptors, sorted by path — deterministic UI ordering.
    pub fn all_descriptors(&self) -> Vec<CommandDescriptor> {
        let mut v: Vec<_> = self.by_path.values().cloned().collect();
        v.sort_by_key(|a| a.path_key());
        v
    }

    /// Build argv for `path` from a caller-supplied parameter map.
    /// `values` keys are declared parameter names; repeatable parameters
    /// accept one value per call — the caller repeats the map entry through
    /// `repeated` (name → values).
    pub fn build_argv(
        &self,
        path: &str,
        values: &BTreeMap<String, String>,
        flags: &[String],
        repeated: &BTreeMap<String, Vec<String>>,
    ) -> Result<Vec<String>, BuildError> {
        let desc = self
            .by_path
            .get(path)
            .ok_or_else(|| BuildError::UnknownCommand(path.into()))?;

        let mut seen: HashMap<&str, usize> = HashMap::new();
        for name in values.keys().chain(flags.iter()).chain(repeated.keys()) {
            let param = desc
                .parameters
                .iter()
                .find(|p| &p.name == name)
                .ok_or_else(|| BuildError::UnknownParameter(name.clone()))?;
            *seen.entry(param.name.as_str()).or_default() += 1;
        }

        let mut argv: Vec<String> = path.split(' ').map(str::to_string).collect();
        let mut missing = Vec::new();

        for param in &desc.parameters {
            let supplied = seen.get(param.name.as_str()).copied().unwrap_or(0);
            if param.required && supplied == 0 {
                missing.push(param.name.clone());
                continue;
            }
            if supplied == 0 {
                continue;
            }
            match param.kind.as_str() {
                "argument" => {
                    if flags.contains(&param.name) {
                        return Err(BuildError::RuleViolation(format!(
                            "{} is a positional argument, not a flag",
                            param.name
                        )));
                    }
                    if let Some(v) = values.get(&param.name) {
                        argv.push(v.clone());
                    }
                    for v in repeated.get(&param.name).into_iter().flatten() {
                        argv.push(v.clone());
                    }
                }
                _ => {
                    let flag = format!("--{}", param.name.replace('_', "-"));
                    if flags.contains(&param.name) {
                        if param.value_type == "boolean" {
                            argv.push(flag.clone());
                        } else {
                            return Err(BuildError::RuleViolation(format!(
                                "{} is not a flag",
                                param.name
                            )));
                        }
                    }
                    if let Some(v) = values.get(&param.name) {
                        if !param.choices.is_empty() && !param.choices.contains(v) {
                            return Err(BuildError::ChoiceViolation {
                                name: param.name.clone(),
                                value: v.clone(),
                            });
                        }
                        argv.push(flag.clone());
                        argv.push(v.clone());
                    }
                    for v in repeated.get(&param.name).into_iter().flatten() {
                        if !param.repeatable {
                            return Err(BuildError::RuleViolation(format!(
                                "{} is not repeatable",
                                param.name
                            )));
                        }
                        argv.push(flag.clone());
                        argv.push(v.clone());
                    }
                }
            }
        }

        if !missing.is_empty() {
            return Err(BuildError::MissingRequired(missing));
        }

        self.check_rules(desc, &seen, values, flags)?;
        Ok(argv)
    }

    fn check_rules(
        &self,
        desc: &CommandDescriptor,
        seen: &HashMap<&str, usize>,
        values: &BTreeMap<String, String>,
        flags: &[String],
    ) -> Result<(), BuildError> {
        let is_set = |n: &str| {
            seen.contains_key(n) || values.contains_key(n) || flags.iter().any(|f| f == n)
        };
        for rule in &desc.parameter_rules {
            let count = rule.parameters.iter().filter(|p| is_set(p)).count();
            // `when_values` may carry the sentinel "present" (the parameter is
            // set to any value) or a closed value list; `when_parameter` may be
            // "" when the rule is unconditional.
            let conditioned = match rule.when_parameter.as_str() {
                "" => true,
                wp if rule.when_values == ["present"] => is_set(wp),
                wp => {
                    values
                        .get(wp)
                        .map(|v| rule.when_values.iter().any(|w| w == v))
                        .unwrap_or(false)
                        || (flags.iter().any(|f| f == wp)
                            && rule.when_values.iter().any(|w| w == "true"))
                }
            };
            match (rule.kind.as_str(), conditioned) {
                ("exactly_one", true) if count != 1 => {
                    return Err(BuildError::RuleViolation(format!(
                        "exactly one of {} required",
                        rule.parameters.join(", ")
                    )))
                }
                ("at_most_one", true) if count > 1 => {
                    return Err(BuildError::RuleViolation(format!(
                        "at most one of {}",
                        rule.parameters.join(", ")
                    )))
                }
                ("required_when", true) if count == 0 => {
                    return Err(BuildError::RuleViolation(format!(
                        "one of {} required when {} is set",
                        rule.parameters.join(", "),
                        rule.when_parameter
                    )))
                }
                ("forbidden_when", true) if count > 0 => {
                    return Err(BuildError::RuleViolation(format!(
                        "{} forbidden when {} is set",
                        rule.parameters.join(", "),
                        rule.when_parameter
                    )))
                }
                _ => {}
            }
        }
        Ok(())
    }
}
