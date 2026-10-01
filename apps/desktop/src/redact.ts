/** Debug-trace redaction: keys that may carry bearer material are masked
 *  before a result lands in the IPC log or a copied diagnostic bundle.
 *  `user_code` stays — it is meant to be read aloud to the user. */

const SECRET_KEY = /(^|_)(device_code|token|secret|password|credential|key)s?$/i;

export function redact(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(redact);
  if (v && typeof v === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, val] of Object.entries(v as Record<string, unknown>)) {
      out[k] = SECRET_KEY.test(k) ? "[redacted]" : redact(val);
    }
    return out;
  }
  return v;
}
