#!/usr/bin/env node
/**
 * Call Moment HTTP APIs with a settings personal access token.
 * Endpoint shapes come from skills/moment/references/api.json — do not invent paths.
 *
 *   MOMENT_BASE_URL   optional, default http://localhost:3000
 *   MOMENT_TOKEN      mmt_ token from 设置 → 接口令牌
 *   MOMENT_BA_TOKEN   internal auth=ba routes only
 */
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const skillDir = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const catalogPath = path.join(skillDir, "references/api.json");

function usage(exit = 1) {
  console.error(`Usage:
  node moment.mjs catalog [--json] [--group MODULE] [--method METHOD] [--path SUBSTR]
  node moment.mjs show METHOD PATH
  node moment.mjs call METHOD PATH [--query k=v] [--json '{...}'] [--file body.json]

Env:
  MOMENT_BASE_URL   default http://localhost:3000
  MOMENT_TOKEN      personal access token (mmt_) from 设置 → 接口令牌
  MOMENT_BA_TOKEN   auth=ba routes only
`);
  process.exit(exit);
}

function parseArgs(argv) {
  const args = { _: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === "--json") {
      const next = argv[i + 1];
      if (next && !next.startsWith("--")) {
        args.json = next;
        i += 1;
      } else {
        args.jsonOut = true;
      }
    } else if (token === "--file") {
      args.file = argv[++i];
    } else if (token === "--query") {
      args.query = args.query ?? [];
      args.query.push(argv[++i]);
    } else if (token === "--group") {
      args.group = argv[++i];
    } else if (token === "--method") {
      args.method = argv[++i];
    } else if (token === "--path") {
      args.path = argv[++i];
    } else if (token === "--help" || token === "-h") {
      args.help = true;
    } else if (token.startsWith("--")) {
      throw new Error(`Unknown flag ${token}`);
    } else {
      args._.push(token);
    }
  }
  return args;
}

function baseUrl() {
  return (process.env.MOMENT_BASE_URL ?? "http://localhost:3000").replace(
    /\/+$/,
    "",
  );
}

function loadCatalog() {
  if (!existsSync(catalogPath)) {
    throw new Error(`Missing ${catalogPath}. Run: pnpm gen:moment-skill`);
  }
  return JSON.parse(readFileSync(catalogPath, "utf8"));
}

function normalizePath(value) {
  if (!value) return value;
  const noQuery = value.split("?")[0];
  return noQuery.startsWith("/") ? noQuery : `/${noQuery}`;
}

function pathTemplate(pathname) {
  return pathname
    .replace(
      /\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi,
      "/:id",
    )
    .replace(/\/\d{4}-\d{2}(?=\/|$)/g, "/:period");
}

function findEndpoint(catalog, method, pathname) {
  const m = method.toUpperCase();
  const exact = catalog.endpoints.find(
    (ep) => ep.method === m && ep.path === pathname,
  );
  if (exact) return exact;
  const templated = pathTemplate(pathname);
  const byTemplate = catalog.endpoints.find(
    (ep) => ep.method === m && ep.path === templated,
  );
  if (byTemplate) return byTemplate;
  const score = (ep) => {
    const epParts = ep.path.split("/");
    const got = pathname.split("/");
    if (ep.method !== m || epParts.length !== got.length) return -1;
    let n = 0;
    for (let i = 0; i < epParts.length; i += 1) {
      if (epParts[i].startsWith(":")) continue;
      if (epParts[i] !== got[i]) return -1;
      n += 1;
    }
    return n;
  };
  let best;
  let bestScore = -1;
  for (const ep of catalog.endpoints) {
    const s = score(ep);
    if (s > bestScore) {
      best = ep;
      bestScore = s;
    }
  }
  return bestScore >= 0 ? best : undefined;
}

function printCatalog(catalog, args) {
  const methodFilter = args.method?.toUpperCase();
  const pathFilter = args.path;
  const groupFilter = args.group;
  const rows = catalog.endpoints.filter((ep) => {
    if (methodFilter && ep.method !== methodFilter) return false;
    if (pathFilter && !ep.path.includes(pathFilter)) return false;
    if (groupFilter && ep.module !== groupFilter) return false;
    return true;
  });
  if (args.jsonOut) {
    console.log(JSON.stringify(rows, null, 2));
    return;
  }
  for (const ep of rows) {
    const auth = ep.auth === "none" ? "" : `  ${ep.auth}`;
    const role = ep.role ? `  role>=${ep.role}` : "";
    const body = ep.body ? `  body=${ep.body.name}` : "";
    const query = ep.query ? `  query=${ep.query.name}` : "";
    const stream = ep.stream ? "  sse" : "";
    console.log(
      `${ep.method.padEnd(6)} ${ep.path}${auth}${role}${query}${body}${stream}`,
    );
  }
  console.error(`# ${rows.length} endpoints`);
}

function printShow(ep) {
  if (!ep) {
    console.error(
      "Endpoint not in catalog. Pass a real METHOD PATH from catalog/show.",
    );
    process.exit(2);
  }
  console.log(`${ep.method} ${ep.path}`);
  console.log(`auth: ${ep.auth}`);
  if (ep.role) console.log(`role: >=${ep.role}`);
  if (ep.stream) console.log("stream: sse");
  if (ep.status?.length) console.log(`status: ${ep.status.join(", ")}`);
  if (ep.comment) console.log(ep.comment);
  for (const slot of ["params", "query", "body"]) {
    if (!ep[slot]) continue;
    console.log(`\n${slot}: ${ep[slot].name} (${ep[slot].origin})`);
    if (ep[slot].schema) console.log(JSON.stringify(ep[slot].schema, null, 2));
    else if (ep[slot].source) console.log(ep[slot].source);
  }
}

function buildQuery(raw) {
  const params = new URLSearchParams();
  for (const item of raw ?? []) {
    if (!item) continue;
    if (item.includes("&") || (item.includes("=") && !item.startsWith("{"))) {
      const nested = new URLSearchParams(item);
      for (const [key, value] of nested) params.append(key, value);
    } else {
      params.append(item, "");
    }
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

function readBody(args) {
  if (args.file) return readFileSync(args.file, "utf8");
  if (args.json !== undefined) return args.json;
  return undefined;
}

function printPayload(res, text) {
  const type = res.headers.get("content-type") ?? "";
  if (res.status >= 300 && res.status < 400) {
    console.log(
      JSON.stringify(
        { status: res.status, location: res.headers.get("location") },
        null,
        2,
      ),
    );
    return;
  }
  if (!text) return;
  if (type.includes("text/event-stream") || type.startsWith("text/")) {
    process.stdout.write(text.endsWith("\n") ? text : `${text}\n`);
    return;
  }
  try {
    console.log(JSON.stringify(JSON.parse(text), null, 2));
  } catch {
    process.stdout.write(text.endsWith("\n") ? text : `${text}\n`);
  }
}

function authHeader(ep) {
  if (ep.auth === "ba") {
    const token = process.env.MOMENT_BA_TOKEN ?? "";
    if (!token) {
      console.error("MOMENT_BA_TOKEN is not set. This route is internal.");
      process.exit(2);
    }
    return `Bearer ${token}`;
  }
  if (ep.auth === "none") return undefined;
  const token = process.env.MOMENT_TOKEN ?? "";
  if (!token) {
    if (ep.auth === "optional") return undefined;
    console.error(
      "No MOMENT_TOKEN. Create one in Moment under 设置 → 接口令牌, then export MOMENT_TOKEN='mmt_…'.",
    );
    console.error(
      "Do not paste the token into chat. MOMENT_BASE_URL defaults to http://localhost:3000.",
    );
    process.exit(2);
  }
  return `Bearer ${token}`;
}

async function callApi(catalog, method, pathname, args) {
  const pathOnly = normalizePath(pathname);
  const ep = findEndpoint(catalog, method, pathOnly);
  if (!ep) {
    console.error(`Not in catalog: ${method.toUpperCase()} ${pathOnly}`);
    console.error(
      "Look up with: node moment.mjs catalog   or   node moment.mjs show METHOD PATH",
    );
    process.exit(2);
  }
  const query = buildQuery(args.query);
  const url = `${baseUrl()}${pathOnly}${query}`;
  const headers = { Accept: "application/json, text/event-stream" };
  const authorization = authHeader(ep);
  if (authorization) headers.Authorization = authorization;
  const body = readBody(args);
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(url, {
    method: ep.method,
    headers,
    body,
    redirect: "manual",
  });
  const text = await res.text();
  printPayload(res, text);
  if (res.status >= 300 && res.status < 400) return;
  if (!res.ok) {
    console.error(`# HTTP ${res.status} ${ep.method} ${pathOnly}`);
    process.exit(1);
  }
}

const args = parseArgs(process.argv.slice(2));
if (args.help || args._.length === 0) usage(args.help ? 0 : 1);

const command = args._[0];

if (command === "catalog") {
  printCatalog(loadCatalog(), args);
} else if (command === "show") {
  if (args._.length < 3) usage();
  printShow(findEndpoint(loadCatalog(), args._[1], normalizePath(args._[2])));
} else if (command === "call") {
  if (args._.length < 3) usage();
  await callApi(loadCatalog(), args._[1], args._[2], args);
} else {
  usage();
}
