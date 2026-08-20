const COMPONENT_RE = /^component_[0-7][0-9A-HJKMNP-TV-Z]{25}$/;
const SETUP_RE = /^setup_[0-7][0-9A-HJKMNP-TV-Z]{25}$/;
const ISO_COUNTRY_RE = /^[A-Z]{2}$/;
const USER_ASSIGNED_COUNTRY_RE = /^(AA|ZZ|Q[M-Z]|X[A-Z])$/;

const CATALOG_OBJECT_RE =
  /^\/(?:en|ru)\/(?:ai\/)?catalog\/(components|setups)\/([^/]+)(?:\/versions\/[^/]+)?\/?$/;
const COUNTRY_RE = /^\/(?:en|ru)\/(?:ai\/)?countries\/([^/]+)\/?$/;

/** Catalog object path whose id cannot exist (invalid brand). */
export function isImpossibleCatalogObjectPath(pathname: string): boolean {
  const match = pathname.match(CATALOG_OBJECT_RE);
  if (!match) return false;
  const kind = match[1];
  const id = match[2] ?? "";
  return kind === "components" ? !COMPONENT_RE.test(id) : !SETUP_RE.test(id);
}

/** Country path that cannot be a catalog market (not ISO or user-assigned). */
export function isImpossibleCountryPath(pathname: string): boolean {
  const match = pathname.match(COUNTRY_RE);
  if (!match) return false;
  const code = match[1] ?? "";
  return !ISO_COUNTRY_RE.test(code) || USER_ASSIGNED_COUNTRY_RE.test(code);
}
