//! Server pacing is returned to the caller; transports never sleep or retry.

use std::time::{Duration, SystemTime, UNIX_EPOCH};
use ureq::http::HeaderMap;

use crate::error::Failure;

// Keep machine details exact for every JSON consumer, including JavaScript.
const MAX_SECONDS: u64 = (1 << 53) - 1;

pub(crate) fn annotate(mut failure: Failure, headers: &HeaderMap, github: bool) -> Failure {
    if let Some(seconds) = delay(headers, github, SystemTime::now()) {
        failure
            .details
            .insert("retry_after_seconds".into(), seconds.into());
    }
    failure
}

fn header<'a>(headers: &'a HeaderMap, name: &str) -> Option<&'a str> {
    let mut values = headers.get_all(name).iter();
    let value = values.next()?.to_str().ok()?;
    if values.next().is_some() || value.len() > 128 {
        return None;
    }
    Some(value.trim_matches([' ', '\t']))
}

fn decimal(value: &str) -> Option<u64> {
    if value.is_empty() || !value.bytes().all(|byte| byte.is_ascii_digit()) {
        return None;
    }
    value.parse().ok().filter(|seconds| *seconds <= MAX_SECONDS)
}

fn until(when: SystemTime, now: SystemTime) -> Option<u64> {
    let remaining = when.duration_since(now).unwrap_or(Duration::ZERO);
    let seconds = remaining
        .as_secs()
        .checked_add(u64::from(remaining.subsec_nanos() != 0))?;
    (seconds <= MAX_SECONDS).then_some(seconds)
}

fn delay(headers: &HeaderMap, github: bool, now: SystemTime) -> Option<u64> {
    header(headers, "Retry-After")
        .and_then(|value| {
            decimal(value).or_else(|| until(httpdate::parse_http_date(value).ok()?, now))
        })
        .or_else(|| {
            if !github || decimal(header(headers, "X-RateLimit-Remaining")?)? != 0 {
                return None;
            }
            let seconds = decimal(header(headers, "X-RateLimit-Reset")?)?;
            until(UNIX_EPOCH.checked_add(Duration::from_secs(seconds))?, now)
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pacing_preserves_long_delays_dates_and_unambiguous_bounds()
    -> Result<(), Box<dyn std::error::Error>> {
        let instant = httpdate::parse_http_date("Sun, 06 Nov 1994 08:49:37 GMT")?;
        let now = instant - Duration::from_millis(1500);
        for (value, expected) in [
            ("0", Some(0)),
            ("3600", Some(3600)),
            ("86400", Some(86400)),
            ("\t120 ", Some(120)),
            ("Sun, 06 Nov 1994 08:49:37 GMT", Some(2)),
            ("Sunday, 06-Nov-94 08:49:37 GMT", Some(2)),
            ("Sun Nov  6 08:49:37 1994", Some(2)),
            ("Sat, 05 Nov 1994 08:49:37 GMT", Some(0)),
            ("-1", None),
            ("+1", None),
            ("1.5", None),
            ("9007199254740992", None),
            ("18446744073709551616", None),
            ("invalid-sensitive-response", None),
        ] {
            let mut headers = HeaderMap::new();
            headers.insert("Retry-After", value.parse()?);
            assert_eq!(delay(&headers, false, now), expected, "{value}");
        }
        let mut headers = HeaderMap::new();
        headers.insert("X-RateLimit-Reset", "784111777".parse()?);
        assert_eq!(delay(&headers, false, now), None);
        assert_eq!(delay(&headers, true, now), None);
        headers.insert("X-RateLimit-Remaining", "1".parse()?);
        assert_eq!(delay(&headers, true, now), None);
        headers.insert("X-RateLimit-Remaining", "0".parse()?);
        assert_eq!(delay(&headers, true, now), Some(2));
        headers.insert("Retry-After", "86400".parse()?);
        assert_eq!(delay(&headers, true, now), Some(86400));
        headers.append("Retry-After", "120".parse()?);
        assert_eq!(delay(&headers, false, now), None);
        Ok(())
    }
}
