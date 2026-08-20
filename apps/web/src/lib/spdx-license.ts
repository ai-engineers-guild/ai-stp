/**
 * Known SPDX license identifiers mapped to official SPDX pages only.
 * Unknown identifiers must not invent a URL.
 */
const SPDX_LICENSE_URLS: Record<string, string> = {
  "0BSD": "https://spdx.org/licenses/0BSD.html",
  "AGPL-3.0-only": "https://spdx.org/licenses/AGPL-3.0-only.html",
  "AGPL-3.0-or-later": "https://spdx.org/licenses/AGPL-3.0-or-later.html",
  "Apache-2.0": "https://spdx.org/licenses/Apache-2.0.html",
  "BSD-2-Clause": "https://spdx.org/licenses/BSD-2-Clause.html",
  "BSD-3-Clause": "https://spdx.org/licenses/BSD-3-Clause.html",
  "BSL-1.0": "https://spdx.org/licenses/BSL-1.0.html",
  "CC-BY-4.0": "https://spdx.org/licenses/CC-BY-4.0.html",
  "CC0-1.0": "https://spdx.org/licenses/CC0-1.0.html",
  "EPL-2.0": "https://spdx.org/licenses/EPL-2.0.html",
  "EUPL-1.2": "https://spdx.org/licenses/EUPL-1.2.html",
  "GPL-2.0-only": "https://spdx.org/licenses/GPL-2.0-only.html",
  "GPL-3.0-only": "https://spdx.org/licenses/GPL-3.0-only.html",
  "GPL-3.0-or-later": "https://spdx.org/licenses/GPL-3.0-or-later.html",
  ISC: "https://spdx.org/licenses/ISC.html",
  "LGPL-2.1-only": "https://spdx.org/licenses/LGPL-2.1-only.html",
  "LGPL-3.0-only": "https://spdx.org/licenses/LGPL-3.0-only.html",
  MIT: "https://spdx.org/licenses/MIT.html",
  "MPL-2.0": "https://spdx.org/licenses/MPL-2.0.html",
  Unlicense: "https://spdx.org/licenses/Unlicense.html",
};

export function spdxLicenseUrl(spdxId: string | null | undefined): string | null {
  if (!spdxId) return null;
  return SPDX_LICENSE_URLS[spdxId] ?? null;
}
