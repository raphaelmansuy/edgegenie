/** Validate raster dimensions before handing compressed bytes to an image decoder. */
export const MEDIA_LIMITS = { bytes: 5 * 1024 * 1024, pixels: 16_000_000, timeout: 10_000 };
let active = 0;
const queue: (() => void)[] = [];
export async function withMediaSlot<T>(signal: AbortSignal, operation: () => Promise<T>): Promise<T> {
  if (signal.aborted) throw new Error("Image request cancelled");
  if (active < 4) active++;
  else await new Promise<void>((resolve, reject) => {
    const start = () => { active++; signal.removeEventListener("abort", cancel); resolve(); };
    const cancel = () => { const at = queue.indexOf(start); if (at >= 0) queue.splice(at, 1); reject(new Error("Image request cancelled")); };
    queue.push(start); signal.addEventListener("abort", cancel, { once: true });
  });
  if (signal.aborted) { active--; queue.shift()?.(); throw new Error("Image request cancelled"); }
  try { return await operation(); } finally { active--; queue.shift()?.(); }
}
export function rasterSize(bytes: Uint8Array): { width: number; height: number } {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (bytes.length >= 24 && [137,80,78,71,13,10,26,10].every((x, i) => bytes[i] === x)) {
    for (let at = 8; at + 12 <= bytes.length;) {
      if (String.fromCharCode(...bytes.slice(at + 4, at + 8)) === "acTL") throw new Error("Animated images are not supported");
      at += view.getUint32(at) + 12;
    }
    return { width: view.getUint32(16), height: view.getUint32(20) };
  }
  if (bytes[0] === 255 && bytes[1] === 216) {
    let at = 2;
    while (at + 8 < bytes.length) {
      if (bytes[at++] !== 255) throw new Error("Invalid JPEG image");
      while (bytes[at] === 255) at++;
      const marker = bytes[at++];
      if (marker === 0xd9 || marker === 0xda) break;
      if (marker === 0x01 || marker >= 0xd0 && marker <= 0xd7) continue;
      if (at + 2 > bytes.length) break;
      const length = view.getUint16(at);
      if (length < 2 || at + length > bytes.length) break;
      if ([0xc0,0xc1,0xc2].includes(marker)) return { height: view.getUint16(at + 3), width: view.getUint16(at + 5) };
      at += length;
    }
  }
  throw new Error("Only valid PNG and JPEG images are supported");
}
export async function readRaster(response: Response): Promise<Blob> {
  if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? "Image unavailable with your permissions." : "Image could not be loaded. Check the reference or retry.");
  if (!/^image\/(png|jpeg)(;|$)/i.test(response.headers.get("content-type") ?? "")) throw new Error("Only PNG and JPEG images are supported.");
  if (Number(response.headers.get("content-length")) > MEDIA_LIMITS.bytes) { await response.body?.cancel(); throw new Error("Image exceeds the 5 MiB limit."); }
  const reader = response.body?.getReader();
  if (!reader) throw new Error("No image content was returned.");
  const chunks: Uint8Array[] = []; let size = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.length;
      if (size > MEDIA_LIMITS.bytes) throw new Error("Image exceeds the 5 MiB limit.");
      chunks.push(value);
    }
  } catch (e) { await reader.cancel().catch(() => {}); throw e; } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size); let at = 0;
  for (const chunk of chunks) { bytes.set(chunk, at); at += chunk.length; }
  const dimensions = rasterSize(bytes);
  if (!dimensions.width || !dimensions.height || dimensions.width * dimensions.height > MEDIA_LIMITS.pixels) throw new Error("Image exceeds the 16 megapixel limit.");
  return new Blob([bytes], { type: response.headers.get("content-type")! });
}
