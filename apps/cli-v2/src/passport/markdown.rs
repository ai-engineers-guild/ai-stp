//! The closed CommonMark description profile, without rendering or extensions.

use pulldown_cmark::{Event, Options, Parser, Tag};
use unicode_general_category::{GeneralCategory, get_general_category};
use unicode_normalization::is_nfc;

use crate::error::{Failure, Result};

fn invalid() -> Failure {
    Failure::precondition("passport description violates the safe Markdown profile")
}

fn link(destination: &str) -> bool {
    if destination.starts_with('#') {
        return destination.len() > 1 && !destination.chars().any(char::is_whitespace);
    }
    if destination.contains('\\') || !destination.starts_with("https://") {
        return false;
    }
    let authority = destination[8..].split(['/', '?', '#']).next().unwrap_or("");
    url::Url::parse(destination).is_ok_and(|url| {
        url.host_str().is_some() && !authority.contains('@') && url.port() != Some(0)
    })
}

pub fn validate(source: &str) -> Result<()> {
    if source.trim().is_empty()
        || source.len() > 16 * 1024
        || source.bytes().filter(|b| *b == b'\n').count() >= 256
        || !is_nfc(source)
        || source.chars().any(|c| {
            c != '\n'
                && c != '\t'
                && matches!(
                    get_general_category(c),
                    GeneralCategory::Control | GeneralCategory::Format | GeneralCategory::Surrogate
                )
        })
    {
        return Err(invalid());
    }
    let mut depth = 0;
    let mut readable = false;
    for event in Parser::new_ext(source, Options::empty()) {
        match event {
            Event::Start(tag) => {
                depth += 1;
                if depth > 32 {
                    return Err(invalid());
                }
                match tag {
                    Tag::Paragraph
                    | Tag::Heading { .. }
                    | Tag::BlockQuote(None)
                    | Tag::CodeBlock(_)
                    | Tag::List(_)
                    | Tag::Item
                    | Tag::Emphasis
                    | Tag::Strong => {}
                    Tag::Link { dest_url, .. } if link(&dest_url) => {}
                    _ => return Err(invalid()),
                }
            }
            Event::End(_) => depth -= 1,
            Event::Text(text) | Event::Code(text) => readable |= !text.trim().is_empty(),
            Event::SoftBreak | Event::HardBreak | Event::Rule => {}
            _ => return Err(invalid()),
        }
    }
    if !readable {
        return Err(invalid());
    }
    Ok(())
}
