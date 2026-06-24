#!/usr/bin/env node
// cybercode CLI launcher — bootstraps a Python env and starts the web UI.
// Designed for `npx cybercode` one-click usage.

import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, copyFileSync, readdirSync, statSync, writeFileSync, readFileSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { homedir, platform } from "node:os";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const __dirname = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const pkg = require("../package.json");

const COLORS = {
  reset: "\x1b[0m", bold: "\x1b[1m", dim: "\x1b[2m",
  green: "\x1b[32m", yellow: "\x1b[33m", blue: "\x1b[34m",
  red: "\x1b[31m", cyan: "\x1b[36m",
};
const c = (color, text) => `${COLORS[color] || ""}${text}${COLORS.reset}`;

function splitCommand(argv) {
  if (argv[0] === "webui") return { command: "webui", args: argv.slice(1) };
  return { command: "webui", args: argv };
}

// ---- Parse CLI args ----
function parseArgs(rawArgv) {
  const args = { port: null, host: "127.0.0.1", dir: null, noBrowser: false, llm: 0, help: false, version: false };
  const argv = rawArgv.slice();
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "-h" || a === "--help") args.help = true;
    else if (a === "-V" || a === "--version") args.version = true;
    else if (a === "-p" || a === "--port") args.port = parseInt(argv[++i], 10);
    else if (a === "--host") args.host = argv[++i];
    else if (a === "--dir") args.dir = argv[++i];
    else if (a === "--no-browser") args.noBrowser = true;
    else if (a === "--llm") args.llm = parseInt(argv[++i], 10);
    else if (a === "--open") args.noBrowser = false;
  }
  return args;
}

function showHelp() {
  console.log(`
${c("bold", "cybercode")} ${c("dim", `v${pkg.version}`)} — Codex-dark web UI with a built-in self-evolving agent

${c("bold", "USAGE")}
  npx cybercode webui                          # start the web UI
  npx cybercode webui --port 8080              # custom port
  npx cybercode webui --host 0.0.0.0           # listen on all interfaces
  npx cybercode webui --no-browser             # don't auto-open browser
  npx cybercode webui --dir ~/my-agent         # custom working directory
  npx cybercode webui --llm 1                  # start on 2nd configured LLM

${c("bold", "OPTIONS")}
  -p, --port <num>     Port (default: auto-find free port near 18600)
  --host <addr>        Bind address (default: 127.0.0.1)
  --dir <path>         Working directory (default: ~/.cybercode)
  --llm <num>          LLM index to start with (default: 0)
  --no-browser         Don't auto-open the browser
  -h, --help           Show this help
  -V, --version        Show version

${c("bold", "FIRST RUN")}
  On first launch, a ${c("cyan", "mykey.json")} template is created in the working
  directory. Edit it with your LLM API keys (OpenAI, DeepSeek, etc.), then
  restart. Any OpenAI-compatible endpoint works.

${c("bold", "ATTRIBUTION")}
  Agent core inspired by GenericAgent (MIT). HyperFrames skills from HeyGen (MIT).
  See LICENSE for details.
`);
}

// ---- Find Python 3.11+ ----
function findPython() {
  const candidates = process.env.WEBUI_CODEX_PYTHON
    ? [process.env.WEBUI_CODEX_PYTHON]
    : ["python3", "python3.12", "python3.11", "python"];

  for (const cmd of candidates) {
    try {
      const result = spawnSync(cmd, ["--version"], { encoding: "utf-8", timeout: 5000 });
      const output = (result.stdout || "") + (result.stderr || "");
      const match = output.match(/Python (\d+)\.(\d+)/);
      if (match) {
        const major = parseInt(match[1], 10);
        const minor = parseInt(match[2], 10);
        if (major > 3 || (major === 3 && minor >= 11)) return cmd;
      }
    } catch {}
  }

  console.error(c("red", "✗ Python 3.11+ not found."));
  console.error(c("dim", "  Install Python 3.11 or 3.12, or set WEBUI_CODEX_PYTHON env var."));
  console.error(c("dim", "  Download: https://www.python.org/downloads/"));
  process.exit(1);
}

// ---- Find a free port ----
function findFreePort(preferred) {
  const start = preferred || 18600;
  for (let port = start; port <= start + 100; port++) {
    try {
      const result = spawnSync("python3", ["-c", `import socket; s=socket.socket(); s.bind(("127.0.0.1",${port})); s.close(); print(${port})`], { encoding: "utf-8", timeout: 3000 });
      if (result.stdout && result.stdout.trim()) return parseInt(result.stdout.trim(), 10);
    } catch {}
  }
  return start;
}

function copyDir(src, dest) {
  if (!existsSync(dest)) mkdirSync(dest, { recursive: true });
  for (const entry of readdirSync(src)) {
    const srcPath = join(src, entry);
    const destPath = join(dest, entry);
    const stat = statSync(srcPath);
    if (stat.isDirectory()) copyDir(srcPath, destPath);
    else copyFileSync(srcPath, destPath);
  }
}

function ensureRequests(python) {
  try {
    const result = spawnSync(python, ["-c", "import requests; print(requests.__version__)"], { encoding: "utf-8", timeout: 5000 });
    if (result.status === 0 && result.stdout.trim()) return;
  } catch {}
  console.log(c("yellow", "→ installing requests..."));
  const install = spawnSync(python, ["-m", "pip", "install", "requests", "--quiet", "--disable-pip-version-check"], { stdio: "inherit", timeout: 60000 });
  if (install.status !== 0) {
    console.error(c("red", "✗ Failed to install requests. Please run: pip install requests"));
    process.exit(1);
  }
}

function waitForServer(url, maxRetries = 30) {
  return new Promise((resolve, reject) => {
    let retries = 0;
    const check = () => {
      import("node:http").then(({ default: http }) => {
        const req = http.get(url, (res) => {
          res.resume();
          if (res.statusCode === 200) resolve();
          else if (++retries < maxRetries) setTimeout(check, 300);
          else reject(new Error("server unhealthy"));
        });
        req.on("error", () => {
          if (++retries < maxRetries) setTimeout(check, 300);
          else reject(new Error("server not responding"));
        });
        req.setTimeout(2000, () => { req.destroy(); if (++retries < maxRetries) setTimeout(check, 300); else reject(new Error("timeout")); });
      });
    };
    check();
  });
}

function openBrowser(url) {
  const cmds = {
    darwin: ["open", [url]],
    win32: ["cmd", ["/c", "start", url]],
    linux: ["xdg-open", [url]],
  };
  const plat = platform();
  const entry = cmds[plat] || cmds.linux;
  try { spawn(entry[0], entry[1], { detached: true, stdio: "ignore" }).unref(); } catch {}
}

async function launchWebUI(rawArgv) {
  const args = parseArgs(rawArgv);
  if (args.help) { showHelp(); process.exit(0); }
  if (args.version) { console.log(pkg.version); process.exit(0); }

  const python = findPython();
  const workDir = resolve(args.dir || join(homedir(), ".cybercode"));
  if (!existsSync(workDir)) mkdirSync(workDir, { recursive: true });

  const stampPath = join(workDir, ".version");
  const currentVersion = pkg.version;
  let needsCopy = true;
  if (existsSync(stampPath)) {
    const stamped = readFileSync(stampPath, "utf-8").trim();
    if (stamped === currentVersion) needsCopy = false;
  }

  const bundledPython = join(__dirname, "..", "python");
  const bundledSkills = join(__dirname, "..", "skills");
  if (needsCopy) {
    if (existsSync(bundledPython)) copyDir(bundledPython, workDir);
    if (existsSync(bundledSkills)) copyDir(bundledSkills, join(workDir, "skills"));
    writeFileSync(stampPath, currentVersion, "utf-8");
  }

  const mykeyPath = join(workDir, "mykey.json");
  if (!existsSync(mykeyPath)) {
    const templatePath = join(__dirname, "..", "templates", "mykey_template.json");
    if (existsSync(templatePath)) copyFileSync(templatePath, mykeyPath);
  }

  let configured = false;
  try {
    const mykey = JSON.parse(readFileSync(mykeyPath, "utf-8"));
    configured = Object.values(mykey).some(v => v.apikey && !String(v.apikey).includes("YOUR-"));
  } catch {}

  ensureRequests(python);
  const port = args.port || findFreePort(18600);
  const url = `http://${args.host}:${port}`;

  console.log();
  console.log(`  ${c("bold", c("blue", "╭─────────────────────────────────────────────────╮"))}`);
  console.log(`  ${c("bold", c("blue", "│"))}  ${c("bold", "cybercode")} ${c("dim", `v${currentVersion}`)}                              ${c("bold", c("blue", "│"))}`);
  console.log(`  ${c("bold", c("blue", "│"))}  ${c("dim", "working dir:")} ${workDir.padEnd(34).slice(0, 34)} ${c("bold", c("blue", "│"))}`);
  console.log(`  ${c("bold", c("blue", "│"))}  ${c("green", `▶ ${url}`)}${" ".repeat(Math.max(0, 33 - url.length))} ${c("bold", c("blue", "│"))}`);
  if (!configured) console.log(`  ${c("bold", c("blue", "│"))}  ${c("yellow", "⚠ edit mykey.json to add your API key")}       ${c("bold", c("blue", "│"))}`);
  console.log(`  ${c("bold", c("blue", "╰─────────────────────────────────────────────────╯"))}`);
  console.log();

  if (!configured) {
    console.log(c("yellow", `  ⚠ mykey.json not configured yet.`));
    console.log(c("dim", `    Edit: ${mykeyPath}`));
    console.log(c("dim", `    Add your OpenAI-compatible API key, then restart.`));
    console.log(c("dim", `    The UI will still load and show a setup banner.`));
    console.log();
  }

  const pyArgs = [join(workDir, "webui_codex.py"), "--port", String(port), "--host", args.host, "--llm_no", String(args.llm)];
  const child = spawn(python, pyArgs, { cwd: workDir, stdio: ["ignore", "pipe", "pipe"], env: { ...process.env, PYTHONUNBUFFERED: "1" } });
  child.stdout.on("data", (data) => process.stdout.write(data));
  child.stderr.on("data", (data) => process.stderr.write(c("dim", data.toString())));
  child.on("error", (err) => { console.error(c("red", `✗ Failed to start: ${err.message}`)); process.exit(1); });
  child.on("exit", (code) => process.exit(code || 0));

  if (!args.noBrowser) {
    try { await waitForServer(`${url}/api/status`, 40); openBrowser(url); }
    catch { console.log(c("dim", `  (browser auto-open skipped — open ${url} manually)`)); }
  }

  process.on("SIGINT", () => { child.kill("SIGINT"); process.exit(0); });
  process.on("SIGTERM", () => { child.kill("SIGTERM"); process.exit(0); });
}

const argv = process.argv.slice(2);
const { command, args } = splitCommand(argv);
if (command === "webui") {
  launchWebUI(args).catch((err) => { console.error(c("red", `✗ ${err.message}`)); process.exit(1); });
} else {
  showHelp();
}
