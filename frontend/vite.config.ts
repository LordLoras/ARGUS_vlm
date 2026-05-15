import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

const defaultAllowedHosts = [".run.pinggy-free.link"];

function splitHosts(value: string | undefined) {
  return (value ?? "")
    .split(",")
    .map((host) => host.trim())
    .filter(Boolean);
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const allowedHosts = [
    ...defaultAllowedHosts,
    ...splitHosts(env.VITE_ALLOWED_HOSTS ?? env.ARGUS_VITE_ALLOWED_HOSTS)
  ];

  return {
    plugins: [react()],
    server: {
      host: env.VITE_DEV_HOST || "127.0.0.1",
      port: Number(env.VITE_DEV_PORT || 5173),
      allowedHosts
    },
    preview: {
      host: env.VITE_DEV_HOST || "127.0.0.1",
      port: Number(env.VITE_DEV_PORT || 5173),
      allowedHosts
    }
  };
});
