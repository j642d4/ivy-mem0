// Mirrors the `basePath` baked into next.config.mjs (via NEXT_BASE_PATH at
// build time). Next.js resolves basePath automatically for <Link>/router
// navigation and _next/* assets, but raw `fetch()` calls and `window.location`
// assignments to the app's own routes need it prefixed manually -- otherwise
// they resolve against the domain root and 404 behind a path-based ALB rule
// (e.g. /mem0/*).
export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";

export function withBasePath(path: string): string {
  return `${BASE_PATH}${path}`;
}
