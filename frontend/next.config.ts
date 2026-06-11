import type { NextConfig } from "next";

// The backend binds to 127.0.0.1 only and is never exposed directly. The frontend
// proxies API + static traffic to it, so one public origin (this app) serves
// everything — required for sharing via a tunnel, safer for local use too.
const BACKEND = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND}/api/:path*` },
      { source: "/static/:path*", destination: `${BACKEND}/static/:path*` },
      { source: "/healthz", destination: `${BACKEND}/healthz` },
      { source: "/readyz", destination: `${BACKEND}/readyz` },
    ];
  },
};

export default nextConfig;
