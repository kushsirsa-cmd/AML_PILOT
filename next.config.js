/** @type {import('next').NextConfig} */
// BACKEND_URL is read at build time: http://127.0.0.1:8000 for the single-container image / local dev,
// http://backend:8000 for docker-compose (set as a build arg).
const BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000";
module.exports = {
  output: "standalone",
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
};
