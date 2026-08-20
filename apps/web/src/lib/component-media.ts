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
  if (!url.startsWith("/v1/media/component/")) return false;
  const id = url.slice("/v1/media/component/".length);
  return Boolean(id) && !id.includes("/") && id.length <= 64;
}

export function isGithubRawUrl(url: string): boolean {
  return url.startsWith("https://raw.githubusercontent.com/");
}

export function isYoutubeVideoId(url: string): boolean {
  return /^[A-Za-z0-9_-]{11}$/.test(url);
}
