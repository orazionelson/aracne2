/**
 * UUIDv4 generator that works in both secure and non-secure browser contexts.
 *
 * `crypto.randomUUID()` is part of the Web Crypto API and is — per the W3C
 * spec — restricted to secure contexts (HTTPS or localhost). On plain HTTP
 * over a LAN address (e.g. http://192.168.x.y:5173) it is `undefined`, so
 * calling it throws `TypeError: crypto.randomUUID is not a function` and
 * blocks every axios request whose interceptor sets X-Request-ID.
 *
 * `crypto.getRandomValues()` is NOT gated by secure context, so we use it
 * as the fallback to assemble a v4 UUID manually. The final fallback
 * (Math.random) is reached only on extremely old browsers without any
 * Web Crypto support; X-Request-ID is a tracing header, not a security
 * token, so a non-CSPRNG path is acceptable as a last resort.
 */
export function makeUuidV4(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}
