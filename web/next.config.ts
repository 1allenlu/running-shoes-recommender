import type { NextConfig } from "next";

// Built as static files (web/out) that FastAPI serves on :8001. `npm run dev` runs on :3000
// and calls the API at NEXT_PUBLIC_API_URL (see .env.development).
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
