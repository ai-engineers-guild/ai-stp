/** Read a binary media body without buffering beyond its configured byte limit. */
export class UploadBodyError extends Error {
  constructor(readonly reason: "empty" | "oversized" | "unreadable") {
    super(reason);
  }
}

export async function readBoundedUpload(request: Request, maxBytes: number): Promise<ArrayBuffer> {
  const reader = request.body?.getReader();
  if (!reader) throw new UploadBodyError("empty");
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    let chunk = await reader.read();
    while (!chunk.done) {
      size += chunk.value.byteLength;
      if (size > maxBytes) {
        await reader.cancel();
        throw new UploadBodyError("oversized");
      }
      chunks.push(chunk.value);
      chunk = await reader.read();
    }
  } catch (error) {
    throw error instanceof UploadBodyError ? error : new UploadBodyError("unreadable");
  } finally {
    reader.releaseLock();
  }
  if (!size) throw new UploadBodyError("empty");
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes.buffer;
}
