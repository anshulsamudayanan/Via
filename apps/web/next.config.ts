import path from "node:path";

import type { NextConfig } from "next";

/**
 * The browser only ever talks to this origin. `/api/*` is proxied to the API
 * service, so session cookies stay same-origin and no API host, storage
 * endpoint or credential is exposed to the browser.
 *
 * VIA_API_INTERNAL_URL is read when the config loads: at `next dev` start, or
 * at `next build` for the standalone production server (a Docker build arg).
 */
const apiUrl = (process.env.VIA_API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/$/, "");
const isDev = process.env.NODE_ENV !== "production";
const maxUploadBodyBytes = Number(process.env.VIA_MAX_UPLOAD_BYTES ?? 50 * 1024 * 1024) + 2 * 1024 * 1024;

const contentSecurityPolicy = [
  "default-src 'self'",
  // Next.js injects inline bootstrap scripts; dev mode additionally needs eval for HMR.
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  `connect-src 'self'${isDev ? " ws:" : ""}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const config: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(process.cwd(), "..", ".."),
  transpilePackages: ["@via/ui", "@via/api-client", "@via/types"],
  poweredByHeader: false,
  experimental: {
    // Next.js buffers proxied request bodies and truncates them at 10 MB by default,
    // which breaks PCB uploads. Must stay above the API's VIA_MAX_UPLOAD_BYTES
    // (+ multipart overhead). See docs/ARCHITECTURE.md "Uploads through the web proxy".
    proxyClientMaxBodySize: maxUploadBodyBytes,
  },
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: contentSecurityPolicy },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default config;
