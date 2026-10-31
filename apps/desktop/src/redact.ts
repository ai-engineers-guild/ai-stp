/** Sanitize diagnostic copies, including temporary device confirmation codes
 *  and verification links. The original reply remains available to the UI. */

const SECRET_KEY =
  /(^|_)(device_code|user_code|verification_uri(?:_complete)?|token|secret|password|credential|key)s?$/i;

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
