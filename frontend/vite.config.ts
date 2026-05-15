import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv, type ProxyOptions } from "vite";

const defaultAllowedHosts = [".run.pinggy-free.link"];
const defaultApiProxyTarget = "http://127.0.0.1:8000";

function splitHosts(value: string | undefined) {
  return (value ?? "")
    .split(",")
    .map((host) => host.trim())
    .filter(Boolean);
}

function buildApiProxy(target: string): Record<string, ProxyOptions> {
  const proxyOptions: ProxyOptions = {
    target,
    changeOrigin: true,
    secure: false
  };

  return {
    "/api": proxyOptions,
    "/data": proxyOptions
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const allowedHosts = [
    ...defaultAllowedHosts,
    ...splitHosts(env.VITE_ALLOWED_HOSTS ?? env.ARGUS_VITE_ALLOWED_HOSTS)
  ];
  const apiProxyTarget =
    env.VITE_API_PROXY_TARGET || env.ARGUS_API_PROXY_TARGET || defaultApiProxyTarget;
  const proxy = buildApiProxy(apiProxyTarget);

  return {
    plugins: [react()],
    server: {
      host: env.VITE_DEV_HOST || "127.0.0.1",
      port: Number(env.VITE_DEV_PORT || 5173),
      allowedHosts,
      proxy
    },
    preview: {
      host: env.VITE_DEV_HOST || "127.0.0.1",
      port: Number(env.VITE_DEV_PORT || 5173),
      allowedHosts,
      proxy
    }
  };
});
