import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Pin the tracing root to this app. Next otherwise walks up looking for a
  // lockfile and can settle on the user's home directory, which makes the
  // production output trace depend on whatever else is on the machine.
  outputFileTracingRoot: here,
  // Glass Box reads from the agent host and writes only approval decisions
  // and routing.yaml. It never shells out to nemoclaw — that would break
  // deploying the frontend separately, which the judges' demo URL depends on.
  env: {
    NEXT_PUBLIC_HOST_URL: process.env.NEXT_PUBLIC_HOST_URL ?? "http://localhost:8000",
    NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/api/stream",
  },
};
export default nextConfig;
