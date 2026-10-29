import type { NextConfig } from "next";
const gateway = process.env.CLIENT_GATEWAY_URL || "http://127.0.0.1:3202";
const config: NextConfig = {
  transpilePackages: ["@hunt/contracts"],
  experimental: { proxyTimeout: 70000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${gateway}/:path*` }];
  },
};
export default config;
