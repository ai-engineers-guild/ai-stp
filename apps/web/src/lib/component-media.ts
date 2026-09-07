/** Client/server shared bounds for component gallery uploads (SPEC-035 REQ-3506). */

export const COMPONENT_MEDIA_MAX_BYTES = 25 * 1024 * 1024;

export const COMPONENT_MEDIA_ALLOWED_MIME = [
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
  "video/mp4",
  "video/webm",
] as const;

export type ComponentMediaMime = (typeof COMPONENT_MEDIA_ALLOWED_MIME)[number];

export const COMPONENT_MEDIA_ACCEPT = COMPONENT_MEDIA_ALLOWED_MIME.join(",");

export function isComponentMediaMime(value: string): value is ComponentMediaMime {
  return (COMPONENT_MEDIA_ALLOWED_MIME as readonly string[]).includes(value);
}

export function kindFromMime(mime: string): "image" | "video" | null {
  if (mime.startsWith("image/") && isComponentMediaMime(mime)) return "image";
  if (mime.startsWith("video/") && isComponentMediaMime(mime)) return "video";
  return null;
}

export function kindFromMediaUrl(value: string): "image" | "video" | "youtube" | null {
  const youtube = normalizeYoutubeUrl(value);
  if (youtube) return "youtube";
  try {
    const pathname = new URL(normalizeGithubUrl(value)).pathname.toLowerCase();
    if (/\.(mp4|webm|mov|m4v)(?:$|\.)/.test(pathname)) return "video";
    if (/\.(jpe?g|png|webp|gif|avif|svg)(?:$|\.)/.test(pathname)) return "image";
  } catch {
    return null;
  }
  return null;
}

export function validateComponentMediaFile(file: File): string | null {
  if (!isComponentMediaMime(file.type)) {
    return "unsupported";
  }
  if (file.size <= 0 || file.size > COMPONENT_MEDIA_MAX_BYTES) {
    return "size";
  }
  return null;
}

export function isUploadedMediaUrl(url: string): boolean {
  const prefix = url.startsWith("/v1/media/setup/") ? "/v1/media/setup/" : "/v1/media/component/";
  if (!url.startsWith(prefix)) return false;
  const id = url.slice(prefix.length);
  return Boolean(id) && !id.includes("/") && id.length <= 64;
}

export function isGithubRawUrl(url: string): boolean {
  return url.startsWith("https://raw.githubusercontent.com/");
}

export function normalizeGithubUrl(value: string): string {
  const url = value.trim();
  const blob = url.match(/^https:\/\/github\.com\/([^/]+)\/([^/]+)\/blob\/([0-9a-f]{40})\/(.+)$/i);
  return blob
    ? `https://raw.githubusercontent.com/${blob[1]}/${blob[2]}/${blob[3]}/${blob[4]}`
    : url;
}

export function normalizeYoutubeUrl(value: string): string | null {
  const url = value.trim();
  if (isYoutubeVideoId(url)) return url;
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.toLowerCase();
    if (!["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"].includes(host)) {
      return null;
    }
    const candidate =
      host === "youtu.be"
        ? parsed.pathname.split("/").filter(Boolean)[0]
        : parsed.pathname === "/watch"
          ? parsed.searchParams.get("v")
          : parsed.pathname.split("/").filter(Boolean)[1];
    return candidate && isYoutubeVideoId(candidate) ? candidate : null;
  } catch {
    return null;
  }
}

export function isExternalMediaUrl(url: string): boolean {
  try {
    const parsed = new URL(url.trim());
    return parsed.protocol === "https:" && Boolean(parsed.hostname);
  } catch {
    return false;
  }
}

export function isYoutubeVideoId(url: string): boolean {
  return /^[A-Za-z0-9_-]{11}$/.test(url);
}
