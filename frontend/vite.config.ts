import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv, type Plugin, type ProxyOptions } from "vite";

declare const Buffer: {
  from(value: string, encoding: "base64"): { toString(encoding: "utf8"): string };
};

const defaultAllowedHosts = [".run.pinggy-free.link"];
const defaultApiProxyTarget = "http://127.0.0.1:8000";

type BasicAuthCredentials = {
  users: Array<{
    username: string;
    password: string;
  }>;
  realm: string;
};

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

function loadBasicAuth(env: Record<string, string | undefined>): BasicAuthCredentials | null {
  if (!parseBoolean(env.ARGUS_BASIC_AUTH_ENABLED)) return null;
  const users = parseBasicAuthUsers(env);
  if (!users.length) {
    throw new Error(
      "ARGUS_BASIC_AUTH_ENABLED is true, but no users are configured. Set ARGUS_BASIC_AUTH_USERS."
    );
  }
  return {
    users,
    realm: env.ARGUS_BASIC_AUTH_REALM?.trim() || "ARGUS"
  };
}

function parseBoolean(value: string | undefined) {
  return ["1", "true", "yes", "on"].indexOf((value ?? "").trim().toLowerCase()) >= 0;
}

function parseBasicAuthUsers(env: Record<string, string | undefined>) {
  const users: BasicAuthCredentials["users"] = [];
  const usersValue = env.ARGUS_BASIC_AUTH_USERS ?? "";
  for (const entry of usersValue.split(/[,\n;]/)) {
    const trimmed = entry.trim();
    if (!trimmed) continue;
    const separator = trimmed.indexOf(":");
    if (separator <= 0) {
      throw new Error("ARGUS_BASIC_AUTH_USERS entries must use username:password format.");
    }
    const username = trimmed.slice(0, separator).trim();
    const password = trimmed.slice(separator + 1).trim();
    if (!username || !password) {
      throw new Error("ARGUS_BASIC_AUTH_USERS entries must include both username and password.");
    }
    users.push({ username, password });
  }

  const username = env.ARGUS_BASIC_AUTH_USERNAME?.trim();
  const password = env.ARGUS_BASIC_AUTH_PASSWORD;
  if (username || password) {
    if (!username || !password) {
      throw new Error("Set both ARGUS_BASIC_AUTH_USERNAME and ARGUS_BASIC_AUTH_PASSWORD.");
    }
    users.push({ username, password });
  }
  return users;
}

function basicAuthPlugin(credentials: BasicAuthCredentials | null): Plugin {
  return {
    name: "argus-basic-auth",
    configureServer(server) {
      if (credentials) server.middlewares.use(createBasicAuthMiddleware(credentials));
    },
    configurePreviewServer(server) {
      if (credentials) server.middlewares.use(createBasicAuthMiddleware(credentials));
    }
  };
}

function createBasicAuthMiddleware(credentials: BasicAuthCredentials): any {
  const expectedCredentials = credentials.users.map((user) => `${user.username}:${user.password}`);
  const realm = credentials.realm.replace(/["\\]/g, "");

  return (
    request: { headers: Record<string, string | string[] | undefined> },
    response: {
      statusCode: number;
      setHeader: (name: string, value: string) => void;
      end: (body: string) => void;
    },
    next: () => void
  ) => {
    const authorization = Array.isArray(request.headers.authorization)
      ? request.headers.authorization[0]
      : request.headers.authorization;

    if (isAuthorized(authorization, expectedCredentials)) {
      next();
      return;
    }

    response.statusCode = 401;
    response.setHeader("WWW-Authenticate", `Basic realm="${realm}", charset="UTF-8"`);
    response.setHeader("Content-Type", "text/plain; charset=utf-8");
    response.setHeader("Cache-Control", "no-store");
    response.end("Authentication required");
  };
}

function isAuthorized(authorization: string | undefined, expectedCredentials: string[]) {
  if (!authorization || authorization.indexOf("Basic ") !== 0) return false;
  const encoded = authorization.slice("Basic ".length).trim();
  let decoded = "";
  try {
    decoded = Buffer.from(encoded, "base64").toString("utf8");
  } catch {
    return false;
  }
  return expectedCredentials.some((expected) => constantTimeEquals(decoded, expected));
}

function constantTimeEquals(left: string, right: string) {
  const maxLength = Math.max(left.length, right.length);
  let mismatch = left.length ^ right.length;
  for (let index = 0; index < maxLength; index += 1) {
    const leftCode = index < left.length ? left.charCodeAt(index) : 0;
    const rightCode = index < right.length ? right.charCodeAt(index) : 0;
    mismatch |= leftCode ^ rightCode;
  }
  return mismatch === 0;
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
  const basicAuth = loadBasicAuth(env);

  return {
    plugins: [basicAuthPlugin(basicAuth), react()],
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
