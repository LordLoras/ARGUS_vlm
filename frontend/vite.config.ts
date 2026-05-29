import { randomBytes } from "node:crypto";
import type { IncomingMessage, ServerResponse } from "node:http";

import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv, type Connect, type Plugin, type ProxyOptions } from "vite";

const defaultAllowedHosts = [".run.pinggy-free.link"];
const defaultApiProxyTarget = "http://127.0.0.1:8000";
const authCookieName = "argus_demo_session";

type AuthMode = "login" | "basic";

type DemoAuthUser = {
  username: string;
  password: string;
};

type DemoAuthConfig = {
  users: DemoAuthUser[];
  realm: string;
  mode: AuthMode;
  sessionTtlSeconds: number;
  secureCookie: boolean | null;
};

type AuthSession = {
  username: string;
  expiresAt: number;
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

function loadDemoAuth(env: Record<string, string | undefined>): DemoAuthConfig | null {
  if (!parseBoolean(env.ARGUS_AUTH_ENABLED ?? env.ARGUS_BASIC_AUTH_ENABLED)) return null;
  const users = parseAuthUsers(env);
  if (!users.length) {
    throw new Error("Auth is enabled, but no users are configured. Set ARGUS_AUTH_USERS.");
  }

  const mode = parseAuthMode(env.ARGUS_AUTH_MODE ?? env.ARGUS_BASIC_AUTH_MODE);
  const ttlHours = Number(env.ARGUS_AUTH_SESSION_TTL_HOURS ?? 12);
  if (!Number.isFinite(ttlHours) || ttlHours <= 0) {
    throw new Error("ARGUS_AUTH_SESSION_TTL_HOURS must be a positive number.");
  }

  return {
    users,
    mode,
    realm: env.ARGUS_AUTH_REALM?.trim() || env.ARGUS_BASIC_AUTH_REALM?.trim() || "ARGUS",
    sessionTtlSeconds: Math.round(ttlHours * 60 * 60),
    secureCookie: parseOptionalBoolean(env.ARGUS_AUTH_SECURE_COOKIE)
  };
}

function parseBoolean(value: string | undefined) {
  return ["1", "true", "yes", "on"].includes((value ?? "").trim().toLowerCase());
}

function parseOptionalBoolean(value: string | undefined): boolean | null {
  if (value == null || value.trim() === "") return null;
  return parseBoolean(value);
}

function parseAuthMode(value: string | undefined): AuthMode {
  const mode = (value ?? "login").trim().toLowerCase();
  if (mode === "login" || mode === "basic") return mode;
  throw new Error('ARGUS_AUTH_MODE must be "login" or "basic".');
}

function parseAuthUsers(env: Record<string, string | undefined>) {
  const users: DemoAuthUser[] = [];
  parseUserList(env.ARGUS_AUTH_USERS ?? env.ARGUS_BASIC_AUTH_USERS, users);

  const username = env.ARGUS_AUTH_USERNAME?.trim() || env.ARGUS_BASIC_AUTH_USERNAME?.trim();
  const password = env.ARGUS_AUTH_PASSWORD ?? env.ARGUS_BASIC_AUTH_PASSWORD;
  if (username || password) {
    if (!username || !password) {
      throw new Error("Set both ARGUS_AUTH_USERNAME and ARGUS_AUTH_PASSWORD.");
    }
    users.push({ username, password });
  }
  return users;
}

function parseUserList(value: string | undefined, users: DemoAuthUser[]) {
  for (const entry of (value ?? "").split(/[,\n;]/)) {
    const trimmed = entry.trim();
    if (!trimmed) continue;
    const separator = trimmed.indexOf(":");
    if (separator <= 0) {
      throw new Error("ARGUS_AUTH_USERS entries must use username:password format.");
    }
    const username = trimmed.slice(0, separator).trim();
    const password = trimmed.slice(separator + 1).trim();
    if (!username || !password) {
      throw new Error("ARGUS_AUTH_USERS entries must include both username and password.");
    }
    users.push({ username, password });
  }
}

function demoAuthPlugin(config: DemoAuthConfig | null): Plugin {
  const sessions: Record<string, AuthSession | undefined> = {};
  return {
    name: "argus-demo-auth",
    configureServer(server) {
      if (config) server.middlewares.use(createAuthMiddleware(config, sessions));
    },
    configurePreviewServer(server) {
      if (config) server.middlewares.use(createAuthMiddleware(config, sessions));
    }
  };
}

function createAuthMiddleware(
  config: DemoAuthConfig,
  sessions: Record<string, AuthSession | undefined>
): Connect.NextHandleFunction {
  const expectedCredentials = config.users.map((user) => `${user.username}:${user.password}`);
  const realm = sanitizeHeaderValue(config.realm);

  return (request, response, next) => {
    const path = getPath(request.url);
    if (config.mode === "basic") {
      handleBasicAuth(request, response, next, expectedCredentials, realm);
      return;
    }

    if (path === "/login" && request.method === "GET") {
      sendLoginPage(response, { redirectTo: getQueryParam(request.url, "redirect") || "/" });
      return;
    }

    if (path === "/auth/login" && request.method === "POST") {
      void handleLoginPost(request, response, config, sessions);
      return;
    }

    if (path === "/auth/logout") {
      clearAuthCookie(response);
      redirect(response, "/login");
      return;
    }

    const session = readSession(request, sessions);
    if (session) {
      next();
      return;
    }

    if (request.method === "GET" && path.startsWith("/api/public")) {
      next();
      return;
    }

    if (path === "/api" || path.startsWith("/api/") || path === "/data" || path.startsWith("/data/")) {
      response.statusCode = 401;
      response.setHeader("Content-Type", "application/json; charset=utf-8");
      response.setHeader("Cache-Control", "no-store");
      response.end('{"detail":"authentication required"}');
      return;
    }

    redirect(response, `/login?redirect=${encodeURIComponent(request.url || "/")}`);
  };
}

function handleBasicAuth(
  request: IncomingMessage,
  response: ServerResponse,
  next: () => void,
  expectedCredentials: string[],
  realm: string
) {
  const authorization = readHeader(request, "authorization");
  if (isBasicAuthorized(authorization, expectedCredentials)) {
    next();
    return;
  }

  response.statusCode = 401;
  response.setHeader("WWW-Authenticate", `Basic realm="${realm}", charset="UTF-8"`);
  response.setHeader("Content-Type", "text/plain; charset=utf-8");
  response.setHeader("Cache-Control", "no-store");
  response.end("Authentication required");
}

async function handleLoginPost(
  request: IncomingMessage,
  response: ServerResponse,
  config: DemoAuthConfig,
  sessions: Record<string, AuthSession | undefined>
) {
  const body = await readRequestBody(request);
  const form = parseForm(body);
  const username = form.username ?? "";
  const password = form.password ?? "";
  const redirectTo = sanitizeRedirect(form.redirect ?? "/");

  const user = config.users.find(
    (candidate) =>
      constantTimeEquals(username, candidate.username) &&
      constantTimeEquals(password, candidate.password)
  );

  if (!user) {
    sendLoginPage(response, {
      redirectTo,
      error: "The username or password is incorrect."
    });
    return;
  }

  const token = createSessionToken();
  sessions[token] = {
    username: user.username,
    expiresAt: Date.now() + config.sessionTtlSeconds * 1000
  };

  response.statusCode = 303;
  response.setHeader("Location", redirectTo);
  response.setHeader("Set-Cookie", buildSessionCookie(token, config, request));
  response.setHeader("Cache-Control", "no-store");
  response.end();
}

function readSession(
  request: IncomingMessage,
  sessions: Record<string, AuthSession | undefined>
): AuthSession | null {
  const token = parseCookies(readHeader(request, "cookie"))[authCookieName];
  if (!token) return null;
  const session = sessions[token];
  if (!session) return null;
  if (session.expiresAt <= Date.now()) {
    delete sessions[token];
    return null;
  }
  return session;
}

function sendLoginPage(
  response: ServerResponse,
  options: { redirectTo: string; error?: string }
) {
  response.statusCode = options.error ? 401 : 200;
  response.setHeader("Content-Type", "text/html; charset=utf-8");
  response.setHeader("Cache-Control", "no-store");
  response.end(renderLoginPage(options.redirectTo, options.error));
}

function renderLoginPage(redirectTo: string, error?: string) {
  const escapedRedirect = escapeHtml(sanitizeRedirect(redirectTo));
  const escapedError = error ? escapeHtml(error) : "";
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>ARGUS Access</title>
    <style>
      :root {
        color-scheme: dark;
        --bg: #06070b;
        --panel: #0d1017;
        --panel-2: #111620;
        --border: #242b38;
        --fg: #f4f7fb;
        --muted: #9aa4b5;
        --quiet: #657083;
        --accent: #7c3aed;
        --accent-2: #00d4a6;
        --danger: #ff6b6b;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background:
          radial-gradient(circle at 18% 12%, #1f355f55, transparent 28rem),
          radial-gradient(circle at 82% 20%, #5b21b655, transparent 30rem),
          linear-gradient(135deg, #050608, #090c12 52%, #050608);
        color: var(--fg);
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      main {
        width: min(440px, calc(100vw - 32px));
        border: 1px solid var(--border);
        border-radius: 10px;
        background: color-mix(in srgb, var(--panel) 92%, transparent);
        box-shadow: 0 30px 90px #000a, inset 0 1px 0 #ffffff0a;
        overflow: hidden;
      }
      .brand {
        padding: 28px 30px 22px;
        border-bottom: 1px solid var(--border);
        background:
          linear-gradient(135deg, #151b28, #0d1017 58%),
          repeating-linear-gradient(0deg, transparent 0 4px, #ffffff05 4px 5px);
      }
      .eyebrow {
        color: var(--accent-2);
        font: 700 11px/1.4 ui-monospace, SFMono-Regular, Consolas, monospace;
        letter-spacing: .14em;
        text-transform: uppercase;
      }
      h1 {
        margin: 8px 0 6px;
        font-size: 34px;
        letter-spacing: 0;
      }
      p {
        margin: 0;
        color: var(--muted);
        line-height: 1.55;
        font-size: 14px;
      }
      form {
        padding: 24px 30px 30px;
        display: grid;
        gap: 14px;
      }
      label {
        display: grid;
        gap: 6px;
        color: var(--muted);
        font-size: 12px;
        font-weight: 650;
      }
      input {
        width: 100%;
        border: 1px solid var(--border);
        border-radius: 7px;
        background: var(--panel-2);
        color: var(--fg);
        padding: 11px 12px;
        font: inherit;
        outline: none;
      }
      input:focus {
        border-color: var(--accent);
        box-shadow: 0 0 0 3px #7c3aed35;
      }
      button {
        margin-top: 4px;
        border: 0;
        border-radius: 7px;
        background: linear-gradient(135deg, var(--accent), #5b21b6);
        color: white;
        padding: 11px 14px;
        font: 800 14px/1.2 inherit;
        cursor: pointer;
      }
      .error {
        border: 1px solid #ff6b6b55;
        background: #3a111855;
        color: #ffc5c5;
        border-radius: 7px;
        padding: 10px 11px;
        font-size: 13px;
      }
      .foot {
        color: var(--quiet);
        font: 11px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace;
      }
    </style>
  </head>
  <body>
    <main>
      <section class="brand">
        <div class="eyebrow">Secure Demo Access</div>
        <h1>ARGUS</h1>
        <p>Ad Retrieval, Graphing &amp; Understanding System</p>
      </section>
      <form method="post" action="/auth/login" autocomplete="on">
        <input type="hidden" name="redirect" value="${escapedRedirect}" />
        ${escapedError ? `<div class="error">${escapedError}</div>` : ""}
        <label>
          Username
          <input name="username" autocomplete="username" autofocus required />
        </label>
        <label>
          Password
          <input name="password" type="password" autocomplete="current-password" required />
        </label>
        <button type="submit">Enter ARGUS</button>
        <div class="foot">Local-first demo gate. Keep the API port private.</div>
      </form>
    </main>
  </body>
</html>`;
}

function readRequestBody(request: IncomingMessage) {
  return new Promise<string>((resolve, reject) => {
    let body = "";
    request.setEncoding("utf8");
    request.on("data", (chunk) => {
      body += chunk;
      if (body.length > 16_384) {
        reject(new Error("request body too large"));
        request.destroy();
      }
    });
    request.on("end", () => resolve(body));
    request.on("error", reject);
  });
}

function parseForm(body: string) {
  const form: Record<string, string> = {};
  for (const part of body.split("&")) {
    if (!part) continue;
    const [rawKey, rawValue = ""] = part.split("=");
    form[decodeFormValue(rawKey)] = decodeFormValue(rawValue);
  }
  return form;
}

function decodeFormValue(value: string) {
  try {
    return decodeURIComponent(value.replace(/\+/g, " "));
  } catch {
    return "";
  }
}

function buildSessionCookie(
  token: string,
  config: DemoAuthConfig,
  request: IncomingMessage
) {
  const secure = config.secureCookie ?? isHttpsRequest(request);
  return [
    `${authCookieName}=${encodeURIComponent(token)}`,
    "Path=/",
    "HttpOnly",
    "SameSite=Lax",
    `Max-Age=${config.sessionTtlSeconds}`,
    secure ? "Secure" : ""
  ]
    .filter(Boolean)
    .join("; ");
}

function clearAuthCookie(response: ServerResponse) {
  response.setHeader(
    "Set-Cookie",
    `${authCookieName}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`
  );
}

function createSessionToken() {
  return randomBytes(32).toString("base64url");
}

function isBasicAuthorized(authorization: string | undefined, expectedCredentials: string[]) {
  if (!authorization?.startsWith("Basic ")) return false;
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

function readHeader(request: IncomingMessage, name: string) {
  const value = request.headers[name.toLowerCase()];
  return Array.isArray(value) ? value[0] : value;
}

function parseCookies(cookieHeader: string | undefined) {
  const cookies: Record<string, string> = {};
  for (const cookie of (cookieHeader ?? "").split(";")) {
    const trimmed = cookie.trim();
    if (!trimmed) continue;
    const separator = trimmed.indexOf("=");
    if (separator <= 0) continue;
    cookies[trimmed.slice(0, separator)] = decodeURIComponent(trimmed.slice(separator + 1));
  }
  return cookies;
}

function getPath(url: string | undefined) {
  return (url || "/").split("?")[0] || "/";
}

function getQueryParam(url: string | undefined, name: string) {
  const query = (url || "").split("?")[1] || "";
  for (const part of query.split("&")) {
    const [rawKey, rawValue = ""] = part.split("=");
    if (decodeFormValue(rawKey) === name) return decodeFormValue(rawValue);
  }
  return "";
}

function sanitizeRedirect(value: string) {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/";
  if (value.startsWith("/auth/") || value.startsWith("/login")) return "/";
  return value;
}

function sanitizeHeaderValue(value: string) {
  return value.replace(/["\\\r\n]/g, "");
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function isHttpsRequest(request: IncomingMessage) {
  const forwardedProto = readHeader(request, "x-forwarded-proto");
  return forwardedProto === "https";
}

function redirect(response: ServerResponse, location: string) {
  response.statusCode = 303;
  response.setHeader("Location", location);
  response.setHeader("Cache-Control", "no-store");
  response.end();
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
  const auth = loadDemoAuth(env);

  return {
    plugins: [demoAuthPlugin(auth), react()],
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            "three-vendor": ["three", "react-force-graph-3d", "three-spritetext"]
          }
        }
      }
    },
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
