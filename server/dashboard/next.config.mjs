/** @type {import('next').NextConfig} */
// Set at build time when the app is served behind a path-based ALB/proxy rule
// that forwards the prefix as-is (e.g. https://host/mem0/* -> this app).
// Leave unset for local dev / deployments served from the domain root.
const basePath = process.env.NEXT_BASE_PATH || "";

const nextConfig = {
  output: "standalone",
  ...(basePath ? { basePath } : {}),
  // Next.js resolves basePath automatically for <Link>/router navigation and
  // _next/* assets, but raw `fetch()`/`window.location` calls to the app's own
  // routes need it prefixed manually. Mirror it here so client code has a
  // single source of truth instead of a separately-configured env var.
  env: {
    NEXT_PUBLIC_BASE_PATH: basePath,
  },
  eslint: {
    ignoreDuringBuilds: false,
  },
  typescript: {
    ignoreBuildErrors: false,
  },
  experimental: {
    optimizePackageImports: ["@/components", "@/lib", "@/utils"],
  },
  compress: true,
  images: {
    formats: ["image/webp", "image/avif"],
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
  redirects: async () => {
    return [
      {
        source: "/settings",
        destination: "/dashboard/settings",
        permanent: false,
      },
    ];
  },
};

export default nextConfig;
