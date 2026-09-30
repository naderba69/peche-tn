import type { NextConfig } from "next";

const staticExport = process.env.PECHE_TN_STATIC_EXPORT === "1";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  typedRoutes: true,
  allowedDevOrigins: ["localhost", "127.0.0.1", "*.e2b.app"],
  ...(staticExport
    ? { output: "export" as const }
    : {
        async headers() {
          return [
            {
              source: "/sw.js",
              headers: [
                { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
                { key: "Service-Worker-Allowed", value: "/" },
              ],
            },
            {
              source: "/offline.html",
              headers: [{ key: "Cache-Control", value: "no-cache, must-revalidate" }],
            },
          ];
        },
        async rewrites() {
          const apiOrigin = process.env.PECHE_TN_API_ORIGIN;
          if (!apiOrigin) return [];
          return [
            {
              source: "/api/:path*",
              destination: `${apiOrigin.replace(/\/$/, "")}/api/:path*`,
            },
          ];
        },
      }),
};

export default nextConfig;
