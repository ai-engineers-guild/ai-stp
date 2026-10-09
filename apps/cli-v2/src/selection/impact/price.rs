//! Explicit decimal price snapshots; never fetch a rate or call a model.

use serde::Deserialize;
use serde_json::{Value, json};

use crate::{
    error::{Failure, Result},
    passport,
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Profile {
    #[serde(default = "one")]
    schema_version: u32,
    profile_id: String,
    tokenizer_profile: String,
    model: String,
    #[serde(default = "usd")]
    currency: String,
    input_per_million: String,
    source: String,
    fetched_at: String,
    expires_at: String,
}

fn one() -> u32 {
    1
}
fn usd() -> String {
    "USD".into()
}
fn invalid() -> Failure {
    Failure::input("the explicit price profile is invalid")
}

pub(super) fn cost(
    budget: &Value,
    estimator: &str,
    raw: Option<&Value>,
    at: &str,
) -> Result<Value> {
    let mut result = json!({"status":"unavailable","amount":null,"currency":null,
        "profile_id":null,"source":null,"fetched_at":null,"reason":"price_profile_not_supplied"});
    let Some(raw) = raw else {
        return Ok(result);
    };
    let profile: Profile = serde_json::from_value(raw.clone()).map_err(|_| invalid())?;
    let id = profile.profile_id.as_bytes();
    let rate = &profile.input_per_million;
    let (whole, fraction) = rate.split_once('.').unwrap_or((rate, ""));
    let url = url::Url::parse(&profile.source).map_err(|_| invalid())?;
    if profile.schema_version != 1
        || profile.currency != "USD"
        || profile.model.is_empty()
        || id.len() < 2
        || !id[0].is_ascii_lowercase() && !id[0].is_ascii_digit()
        || !id
            .iter()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || b"._-".contains(c))
        || whole.is_empty()
        || !whole.bytes().all(|b| b.is_ascii_digit())
        || !fraction.bytes().all(|b| b.is_ascii_digit())
        || (rate.contains('.') && fraction.is_empty())
        || rate.len() > 4096
        || url.scheme() != "https"
        || url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
        || profile.source.chars().any(char::is_whitespace)
        || !passport::timestamp(&profile.fetched_at)
        || !passport::timestamp(&profile.expires_at)
        || profile.expires_at <= profile.fetched_at
    {
        return Err(invalid());
    }
    if profile.tokenizer_profile != estimator {
        return Err(Failure::input("the price profile uses another estimator"));
    }
    result["currency"] = profile.currency.into();
    result["profile_id"] = profile.profile_id.into();
    result["source"] = profile.source.into();
    result["fetched_at"] = profile.fetched_at.clone().into();
    if at > profile.expires_at.as_str() {
        result["status"] = "stale".into();
        result["reason"] = "price_profile_expired".into();
    } else if at < profile.fetched_at.as_str() {
        result["reason"] = "price_profile_not_yet_valid".into();
    } else if budget["unavailable_components"] != 0 {
        result["reason"] = "context_budget_unavailable".into();
    } else {
        let total = budget["always_tokens"].as_u64().ok_or_else(invalid)?
            + budget["conditional_tokens"].as_u64().ok_or_else(invalid)?;
        result["status"] = "available".into();
        result["amount"] = amount(whole, fraction, total).into();
        result["reason"] = Value::Null;
    }
    Ok(result)
}

/// Multiply decimal digits by the bounded unit count, then round half-up to
/// eight places after division by one million. No floating-point intermediate.
fn amount(whole: &str, fraction: &str, count: u64) -> String {
    let mut digits = Vec::new();
    let mut carry = 0_u128;
    for byte in whole.bytes().chain(fraction.bytes()).rev() {
        let value = u128::from(byte - b'0') * u128::from(count) + carry;
        digits.push((value % 10) as u8);
        carry = value / 10;
    }
    while carry != 0 {
        digits.push((carry % 10) as u8);
        carry /= 10;
    }
    if fraction.len() <= 2 {
        digits.splice(0..0, std::iter::repeat_n(0, 2 - fraction.len()));
    } else {
        let removed = fraction.len() - 2;
        let round_up = digits.get(removed - 1).is_some_and(|digit| *digit >= 5);
        digits.drain(..removed.min(digits.len()));
        if round_up {
            let mut index = 0;
            loop {
                if index == digits.len() {
                    digits.push(1);
                    break;
                }
                if digits[index] < 9 {
                    digits[index] += 1;
                    break;
                }
                digits[index] = 0;
                index += 1;
            }
        }
    }
    while digits.len() > 9 && digits.last() == Some(&0) {
        digits.pop();
    }
    digits.resize(digits.len().max(9), 0);
    let mut text: String = digits
        .into_iter()
        .rev()
        .map(|digit| char::from(b'0' + digit))
        .collect();
    text.insert(text.len() - 8, '.');
    text
}
