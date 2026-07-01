#!/usr/bin/env node
// cybercode CLI launcher -- bootstraps a Python env and starts the web UI.
// Supports: npm install -g cybercode-cli && cybercode

import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, copyFileSync, readdirSync, statSync, writeFileSync, readFileSync, unlinkSync, rmSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { homedir, platform } from "node:os";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const __dirname = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const pkg = require("../package.json");

// ---- Fix Windows console encoding (CP936 -> UTF-8) ----
if (platform() === "win32") {
  try {
    spawnSync("chcp", ["65001"], { stdio: "ignore", shell: true });
    if (process.stdout.isTTY && typeof process.stdout._handle?.setBlocking === "function") {
      process.stdout._handle.setBlocking(true);
    }
  } catch {}
}

const COLORS = {
  reset: "\x1b[0m", bold: "\x1b[1m", dim: "\x1b[2m",
  green: "\x1b[32m", yellow: "\x1b[33m", blue: "\x1b[34m",
  red: "\x1b[31m", cyan: "\x1b[36m", magenta: "\x1b[35m",
};
const c = (color, text) => `${COLORS[color] || ""}${text}${COLORS.reset}`;

// ---- Update check ----
async function checkForUpdates() {
  try {
    const registryUrl = `https://registry.npmjs.org/${pkg.name}/latest`;
    const res = await fetch(registryUrl, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) return;
    const data = await res.json();
    const latest = data.version;
    if (latest && latest !== pkg.version) {
      const isGlobal = __dirname.includes("node_modules");
      const updateCmd = isGlobal ? `npm update -g ${pkg.name}` : `npm install ${pkg.name}@latest`;
      console.log(c("yellow", `\n  +-- Update available -----------------------+`));
      console.log(c("yellow", `  |  ${c("bold", pkg.name)} ${c("dim", pkg.version)} -> ${c("green", latest)}${" ".repeat(Math.max(0, 24 - latest.length))}|`));
      console.log(c("yellow", `  |  Run: ${c("cyan", updateCmd)}${" ".repeat(Math.max(0, 37 - updateCmd.length))}|`));
      console.log(c("yellow", `  +--------------------------------------------+\n`));
    }
  } catch {}
}

function splitCommand(argv) {
  if (argv[0] === "webui") return { command: "webui", args: argv.slice(1) };
  if (argv[0] === "update") return { command: "update", args: argv.slice(1) };
  if (argv[0] === "doctor") return { command: "doctor", args: argv.slice(1) };
  if (argv[0] === "logout") return { command: "logout", args: argv.slice(1) };
  return { command: "webui", args: argv };
}

// ---- Parse CLI args ----
function parseArgs(rawArgv) {
  const args = { port: null, host: "127.0.0.1", dir: null, noBrowser: false, llm: -1, help: false, version: false };
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
${c("bold", "cybercode")} ${c("dim", `v${pkg.version}`)} -- Codex-dark web UI with a built-in self-evolving agent

${c("bold", "INSTALL")}
  ${c("green", "npm install -g cybercode-cli")}
  ${c("dim", "# or: npm i -g cybercode-cli")}

${c("bold", "USAGE")}
  ${c("cyan", "cybercode")}                                # start the web UI
  ${c("cyan", "cybercode")} webui --port 8080              # custom port
  ${c("cyan", "cybercode")} webui --host 0.0.0.0           # listen on all interfaces
  ${c("cyan", "cybercode")} webui --no-browser             # don't auto-open browser
  ${c("cyan", "cybercode")} webui --dir ~/my-agent         # custom working directory
  ${c("cyan", "cybercode")} webui --llm 1                  # start on 2nd configured LLM
  ${c("cyan", "cybercode")} update                         # check & install latest version
  ${c("cyan", "cybercode")} doctor                         # run diagnostics
  ${c("cyan", "cybercode")} logout                         # log out and clear all credentials

${c("bold", "OPTIONS")}
  -p, --port <num>     Port (default: auto-find free port near 18600)
  --host <addr>        Bind address (default: 127.0.0.1)
  --dir <path>         Working directory (default: ~/.cybercode)
  --llm <num>          LLM index to start with (default: -1 = auto)
  --no-browser         Don't auto-open the browser
  -h, --help           Show this help
  -V, --version        Show version

${c("bold", "FIRST RUN")}
  On first launch, a ${c("cyan", "mykey.json")} template is created in the working
  directory. Edit it with your LLM API keys, then restart.
  Or just log in via the web UI (requires l0veyou backend).

${c("bold", "UPDATE")}
  ${c("cyan", "cybercode update")}                         # self-update to latest
  ${c("dim", "# or: npm update -g cybercode-cli")}

${c("bold", "ATTRIBUTION")}
  Agent core inspired by GenericAgent (MIT). HyperFrames skills from HeyGen (MIT).
  See LICENSE for details.
`);
}

// ---- Self-update ----
async function selfUpdate() {
  console.log(c("blue", `\n  Checking for updates...\n`));
  try {
    const registryUrl = `https://registry.npmjs.org/${pkg.name}/latest`;
    const res = await fetch(registryUrl, { signal: AbortSignal.timeout(10000) });
    if (!res.ok) throw new Error("registry unavailable");
    const data = await res.json();
    const latest = data.version;

    if (latest === pkg.version) {
      console.log(c("green", `  OK Already on latest version (${pkg.version})\n`));
      process.exit(0);
    }

    console.log(c("yellow", `  Update available: ${pkg.version} -> ${latest}\n`));
    console.log(c("dim", `  Running: npm install -g ${pkg.name}@latest\n`));

    const result = spawnSync("npm", ["install", "-g", `${pkg.name}@latest`], { stdio: "inherit", shell: true });
    if (result.status === 0) {
      console.log(c("green", `\n  OK Updated to ${latest}\n`));
    } else {
      console.error(c("red", `\n  X Update failed. Try manually: npm install -g ${pkg.name}@latest\n`));
    }
    process.exit(result.status || 0);
  } catch (e) {
    console.error(c("red", `\n  X Cannot check updates: ${e.message}\n`));
    process.exit(1);
  }
}

// ---- Doctor diagnostics ----
async function runDoctor() {
  console.log(c("bold", c("blue", `\n  cybercode doctor -- diagnostics\n`)));
  let allOk = true;

  // Check Node
  const nodeVer = process.versions.node;
  const nodeMajor = parseInt(nodeVer.split(".")[0], 10);
  if (nodeMajor >= 18) {
    console.log(c("green", `  OK Node.js v${nodeVer}`));
  } else {
    console.log(c("red", `  X Node.js v${nodeVer} (need >=18)`));
    allOk = false;
  }

  // Check Python
  const python = findPython(true);
  if (python) {
    console.log(c("green", `  OK Python: ${python}`));
  } else {
    console.log(c("red", `  X Python 3.8+ not found`));
    allOk = false;
  }

  // Check requests
  if (python) {
    try {
      const result = spawnSync(python, ["-c", "import requests; print(requests.__version__)"], { encoding: "utf-8", timeout: 5000 });
      if (result.status === 0) {
        console.log(c("green", `  OK requests ${result.stdout.trim()}`));
      } else {
        console.log(c("yellow", `  ! requests not installed (will auto-install on first run)`));
      }
    } catch {
      console.log(c("yellow", `  ! requests check failed`));
    }
  }

  // Check working dir
  const workDir = join(homedir(), ".cybercode");
  if (existsSync(workDir)) {
    console.log(c("green", `  OK Working dir: ${workDir}`));
  } else {
    console.log(c("dim", `  ○ Working dir not created yet (will create on first run): ${workDir}`));
  }

  // Check for updates
  try {
    const registryUrl = `https://registry.npmjs.org/${pkg.name}/latest`;
    const res = await fetch(registryUrl, { signal: AbortSignal.timeout(5000) });
    const data = await res.json();
    const latest = data.version;
    if (latest === pkg.version) {
      console.log(c("green", `  OK cybercode-cli v${pkg.version} (latest)`));
    } else {
      console.log(c("yellow", `  ! Update available: ${pkg.version} -> ${latest}`));
      console.log(c("dim", `    Run: cybercode update`));
    }
  } catch {
    console.log(c("dim", `  ○ Cannot check npm registry`));
  }

  console.log(allOk ? c("green", c("bold", `\n  All checks passed.\n`)) : c("yellow", c("bold", `\n  Some checks need attention.\n`)));
  process.exit(0);
}

// ---- Find Python 3.8+ ----
function findPython(quiet) {
  const candidates = process.env.CYBERCODE_PYTHON
    ? [process.env.CYBERCODE_PYTHON]
    : ["python3", "python3.12", "python3.11", "python3.10", "python3.9", "python3.8", "python"];

  for (const cmd of candidates) {
    try {
      const result = spawnSync(cmd, ["--version"], { encoding: "utf-8", timeout: 5000 });
      const output = (result.stdout || "") + (result.stderr || "");
      const match = output.match(/Python (\d+)\.(\d+)/);
      if (match) {
        const major = parseInt(match[1], 10);
        const minor = parseInt(match[2], 10);
        if (major > 3 || (major === 3 && minor >= 8)) return cmd;
      }
    } catch {}
  }

  if (!quiet) {
    console.error(c("red", "X Python 3.8+ not found."));
    console.error(c("dim", "  Install Python 3.8+, or set CYBERCODE_PYTHON env var."));
    console.error(c("dim", "  Download: https://www.python.org/downloads/"));
    process.exit(1);
  }
  return null;
}

// ---- Find a free port ----
function findFreePort(preferred, python) {
  const start = preferred || 18600;
  for (let port = start; port <= start + 100; port++) {
    try {
      const result = spawnSync(python || "python", ["-c", `import socket; s=socket.socket(); s.bind(("127.0.0.1",${port})); s.close(); print(${port})`], { encoding: "utf-8", timeout: 3000 });
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
  console.log(c("yellow", "-> installing requests..."));
  const install = spawnSync(python, ["-m", "pip", "install", "requests", "--quiet", "--disable-pip-version-check"], { stdio: "inherit", timeout: 60000 });
  if (install.status !== 0) {
    console.error(c("red", "X Failed to install requests. Please run: pip install requests"));
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

  // Fire update check in background (non-blocking)
  checkForUpdates();

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
  const port = args.port || findFreePort(18600, python);
  const url = `http://${args.host}:${port}`;

  // ASCII art logo (pure ASCII, no Unicode box-drawing)
  const cyan = COLORS.cyan, blue = COLORS.blue, green = COLORS.green, dim = COLORS.dim, bold = COLORS.bold, yellow = COLORS.yellow, reset = COLORS.reset;

  const logo = [
    `  ${cyan}  ___ ___  _  _ ___ ___ ___ ___   ${reset}`,
    `  ${cyan} / __| _ \\| \\| |   \\ __| _ \\ __|  ${reset}`,
    `  ${cyan}| (__|   /| .'| |) | _||   /__|  ${reset}`,
    `  ${cyan} \\___|_|_\\|_|\\_|___/|___|_|_\\___| ${reset}`,
  ];

  const line = `  ${blue}+---------------------------------------+${reset}`;
  const pad = (s, n) => s + " ".repeat(Math.max(0, n - s.length));

  console.log();
  for (const l of logo) console.log(l);
  console.log();
  console.log(line);
  console.log(`  ${blue}|${reset}  ${bold}cybercode${reset} ${dim}v${currentVersion}${reset}${pad("", 25 - currentVersion.length)}${blue}|${reset}`);
  console.log(`  ${blue}|${reset}  ${dim}${pad("working dir:", 36)}${blue}|${reset}`);
  console.log(`  ${blue}|${reset}    ${dim}${pad(workDir, 34)}${blue}|${reset}`);
  console.log(`  ${blue}|${reset}  ${green}> ${url}${reset}${pad("", 35 - url.length)}${blue}|${reset}`);
  if (!configured) console.log(`  ${blue}|${reset}  ${yellow}! edit mykey.json to add your API key${reset}  ${blue}|${reset}`);
  console.log(line);
  console.log();

  if (!configured) {
    console.log(c("yellow", `  ! mykey.json not configured yet.`));
    console.log(c("dim", `    Edit: ${mykeyPath}`));
    console.log(c("dim", `    Or log in via the web UI (requires l0veyou backend).`));
    console.log();
  }

  const pyArgs = [join(workDir, "cybercodewebui.py"), "--port", String(port), "--host", args.host];
  if (args.llm >= 0) pyArgs.push("--llm_no", String(args.llm));
  const child = spawn(python, pyArgs, { cwd: workDir, stdio: ["ignore", "pipe", "pipe"], env: { ...process.env, PYTHONUNBUFFERED: "1" } });
  child.stdout.on("data", (data) => process.stdout.write(data));
  child.stderr.on("data", (data) => process.stderr.write(c("dim", data.toString())));
  child.on("error", (err) => { console.error(c("red", `X Failed to start: ${err.message}`)); process.exit(1); });
  child.on("exit", (code) => process.exit(code || 0));

  if (!args.noBrowser) {
    try { await waitForServer(`${url}/api/status`, 40); openBrowser(url); }
    catch { console.log(c("dim", `  (browser auto-open skipped -- open ${url} manually)`)); }
  }

  process.on("SIGINT", () => { child.kill("SIGINT"); process.exit(0); });
  process.on("SIGTERM", () => { child.kill("SIGTERM"); process.exit(0); });
}

// ---- Logout ----
async function runLogout() {
  const workDir = join(homedir(), ".cybercode");
  let cleared = 0;
  const removed = [];
  let killedProcs = 0;

  // 1. Kill any running cybercodewebui.py process
  try {
    if (platform() === "win32") {
      // Find PIDs running cybercodewebui.py
      const out = spawnSync("wmic", ["process", "where", "name='python.exe'", "get", "processid,commandline"], { encoding: "utf-8", shell: true });
      const lines = (out.stdout || "").split("\n");
      for (const line of lines) {
        if (line.toLowerCase().includes("cybercodewebui")) {
          const pid = line.trim().split(/\s+/).pop();
          if (pid && /^\d+$/.test(pid)) {
            spawnSync("taskkill", ["/F", "/PID", pid], { stdio: "ignore", shell: true });
            killedProcs++;
          }
        }
      }
      // Also kill python3.exe
      const out2 = spawnSync("wmic", ["process", "where", "name='python3.exe'", "get", "processid,commandline"], { encoding: "utf-8", shell: true });
      const lines2 = (out2.stdout || "").split("\n");
      for (const line of lines2) {
        if (line.toLowerCase().includes("cybercodewebui")) {
          const pid = line.trim().split(/\s+/).pop();
          if (pid && /^\d+$/.test(pid)) {
            spawnSync("taskkill", ["/F", "/PID", pid], { stdio: "ignore", shell: true });
            killedProcs++;
          }
        }
      }
    } else {
      const out = spawnSync("pgrep", ["-f", "cybercodewebui.py"], { encoding: "utf-8" });
      const pids = (out.stdout || "").trim().split("\n").filter(Boolean);
      for (const pid of pids) {
        spawnSync("kill", ["-9", pid], { stdio: "ignore" });
        killedProcs++;
      }
    }
  } catch {}

  // 2. Remove credential files
  const authToken = join(workDir, ".auth_token");
  if (existsSync(authToken)) { try { unlinkSync(authToken); cleared++; removed.push(".auth_token"); } catch {} }

  const mykeyPath = join(workDir, "mykey.json");
  if (existsSync(mykeyPath)) { try { unlinkSync(mykeyPath); cleared++; removed.push("mykey.json"); } catch {} }

  const mykeyPyPath = join(workDir, "mykey.py");
  if (existsSync(mykeyPyPath)) { try { unlinkSync(mykeyPyPath); cleared++; removed.push("mykey.py"); } catch {} }

  const promptPath = join(workDir, "custom_system_prompt.txt");
  if (existsSync(promptPath)) { try { unlinkSync(promptPath); cleared++; removed.push("custom_system_prompt.txt"); } catch {} }

  // 3. Remove __pycache__ to force recompile on next start
  const pycache = join(workDir, "__pycache__");
  if (existsSync(pycache)) { try { rmSync(pycache, { recursive: true, force: true }); } catch {} }

  if (cleared > 0 || killedProcs > 0) {
    console.log(c("green", `\n  OK Logged out successfully.`));
    if (cleared > 0) {
      console.log(c("dim", `  Removed: ${removed.join(", ")}`));
    }
    if (killedProcs > 0) {
      console.log(c("dim", `  Stopped ${killedProcs} running process(es)`));
    }
    console.log(c("dim", `  Next run: ${c("cyan", "cybercode web")} will start fresh.\n`));
  } else {
    console.log(c("yellow", `\n  ○ No active session found. Already logged out.\n`));
  }
}

const argv = process.argv.slice(2);
const { command, args } = splitCommand(argv);
if (command === "webui") {
  launchWebUI(args).catch((err) => { console.error(c("red", `X ${err.message}`)); process.exit(1); });
} else if (command === "update") {
  selfUpdate().catch((err) => { console.error(c("red", `X ${err.message}`)); process.exit(1); });
} else if (command === "doctor") {
  runDoctor().catch((err) => { console.error(c("red", `X ${err.message}`)); process.exit(1); });
} else if (command === "logout") {
  runLogout();
} else {
  showHelp();
}
