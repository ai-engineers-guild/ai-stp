//! Pinned Python grammar, without an interpreter or execution of project code.

use std::{ops::ControlFlow, time::Instant};

use tree_sitter::{Node, ParseOptions, Parser};

use super::{DEADLINE, MAX_SYMBOLS, Outline};
use crate::error::{Failure, Result};

pub(super) struct Reader(Parser);

fn text<'a>(node: Node<'_>, source: &'a str) -> &'a str {
    source.get(node.byte_range()).unwrap_or("")
}

fn public(node: Node<'_>, source: &str) -> bool {
    !text(node, source).starts_with('_')
}

fn uppercase(name: &str) -> bool {
    name.chars().any(char::is_uppercase) && !name.chars().any(char::is_lowercase)
}

fn main_guard(node: Node<'_>, source: &str) -> bool {
    let Some(condition) = node.child_by_field_name("condition") else {
        return false;
    };
    if condition.kind() != "comparison_operator" || condition.named_child_count() != 2 {
        return false;
    }
    let Some(operator) = condition.child_by_field_name("operators") else {
        return false;
    };
    if text(operator, source) != "==" {
        return false;
    }
    let mut named = false;
    let mut valued = false;
    let mut cursor = condition.walk();
    for part in condition.named_children(&mut cursor) {
        named |= part.kind() == "identifier" && text(part, source) == "__name__";
        // Accept ordinary literal spelling only; interpolation/escapes are not
        // evidence that the runtime value equals this entry-point sentinel.
        valued |=
            part.kind() == "string" && matches!(text(part, source), "'__main__'" | "\"__main__\"");
    }
    named && valued
}

impl Reader {
    pub(super) fn new() -> Result<Self> {
        let mut parser = Parser::new();
        parser
            .set_language(&tree_sitter_python::LANGUAGE.into())
            .map_err(|_| Failure::precondition("the Python outline grammar is incompatible"))?;
        Ok(Self(parser))
    }

    pub(super) fn read(
        &mut self,
        source: &str,
        started: Instant,
    ) -> std::result::Result<Outline, &'static str> {
        self.0.reset();
        let mut progress = |_: &tree_sitter::ParseState| {
            if started.elapsed() >= DEADLINE {
                ControlFlow::Break(())
            } else {
                ControlFlow::Continue(())
            }
        };
        let tree = self
            .0
            .parse_with_options(
                &mut |offset, _| source.as_bytes().get(offset..).unwrap_or_default(),
                None,
                Some(ParseOptions::new().progress_callback(&mut progress)),
            )
            .ok_or("time budget")?;
        let root = tree.root_node();
        if root.has_error() {
            return Err("the pinned Python grammar could not parse the source");
        }
        let mut outline = Outline {
            symbols: 0,
            entry: false,
        };
        let mut cursor = root.walk();
        for mut node in root.named_children(&mut cursor) {
            if started.elapsed() >= DEADLINE {
                return Err("time budget");
            }
            if node.kind() == "decorated_definition" {
                node = node
                    .child_by_field_name("definition")
                    .ok_or("invalid Python declaration")?;
            }
            match node.kind() {
                "class_definition" | "function_definition" => {
                    let name = node
                        .child_by_field_name("name")
                        .ok_or("invalid Python declaration")?;
                    if public(name, source) {
                        outline.symbols += 1;
                        outline.entry |=
                            node.kind() == "function_definition" && text(name, source) == "main";
                    }
                }
                "expression_statement" => {
                    let Some(mut assignment) = node.named_child(0) else {
                        continue;
                    };
                    let mut depth = 0;
                    while assignment.kind() == "assignment" {
                        depth += 1;
                        if depth > 128 {
                            return Err("declaration depth budget");
                        }
                        if let Some(left) = assignment.child_by_field_name("left")
                            && left.kind() == "identifier"
                            && uppercase(text(left, source))
                        {
                            outline.symbols += 1;
                        }
                        let Some(right) = assignment.child_by_field_name("right") else {
                            break;
                        };
                        assignment = right;
                    }
                }
                "if_statement" => outline.entry |= main_guard(node, source),
                _ => (),
            }
            if outline.symbols > MAX_SYMBOLS {
                return Err("symbol budget");
            }
        }
        Ok(outline)
    }
}
