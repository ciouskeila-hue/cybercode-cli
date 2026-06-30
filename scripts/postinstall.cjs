#!/usr/bin/env node
/**
 * postinstall.cjs — Ensure `cybercode` is available on PATH.
 * Runs automatically after `npm install -g cybercode-cli`.
 * On Windows, adds the npm global bin dir to the user PATH if missing.
 */
const { execSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const platform = process.platform;

if (platform === "win32") {
  let prefix;
  try {
    prefix = execSync("npm config get prefix", { encoding: "utf-8" }).trim();
  } catch {
    process.exit(0);
  }

  const binDir = prefix;
  let userPath = "";
  try {
    const out = execSync('reg query "HKCU\\Environment" /v Path', { encoding: "utf-8" });
    const m = out.match(/Path\s+REG_(?:EXPAND_)?SZ\s+(.+)/);
    if (m) userPath = m[1].trim();
  } catch {}

  const pathParts = userPath ? userPath.split(";").map(p => p.trim().toLowerCase()) : [];
  if (pathParts.includes(binDir.toLowerCase())) {
    process.exit(0);
  }

  let sysPath = "";
  try {
    const out = execSync('reg query "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment" /v Path', { encoding: "utf-8" });
    const m = out.match(/Path\s+REG_(?:EXPAND_)?SZ\s+(.+)/);
    if (m) sysPath = m[1].trim();
  } catch {}

  const sysParts = sysPath ? sysPath.split(";").map(p => p.trim().toLowerCase()) : [];
  if (sysParts.includes(binDir.toLowerCase())) {
    process.exit(0);
  }

  const newPath = userPath ? (userPath.replace(/;$/, "") + ";" + binDir) : binDir;
  try {
    execSync(
      `powershell -NoProfile -Command "[Environment]::SetEnvironmentVariable('Path', '${newPath.replace(/'/g, "''")}', 'User')"`,
      { stdio: "ignore" }
    );
    console.log(`\n  \u2713 Added ${binDir} to user PATH`);
    console.log("  \u2713 Open a NEW terminal for 'cybercode' command to take effect.\n");
  } catch {
    try {
      execSync(`setx PATH "${newPath}"`, { stdio: "ignore" });
      console.log(`\n  \u2713 Added ${binDir} to user PATH (via setx)`);
      console.log("  \u2713 Open a NEW terminal for 'cybercode' command to take effect.\n");
    } catch {
      console.log(`\n  \u26a0 Could not auto-add to PATH. Please add manually: ${binDir}\n`);
    }
  }

  // Also create a cybercode.cmd shim in standard npm location
  const stdNpmDir = path.join(process.env.APPDATA || "", "npm");
  try {
    if (!fs.existsSync(stdNpmDir)) {
      fs.mkdirSync(stdNpmDir, { recursive: true });
    }
    if (sysParts.includes(stdNpmDir.toLowerCase()) || pathParts.includes(stdNpmDir.toLowerCase())) {
      const cmdPath = path.join(stdNpmDir, "cybercode.cmd");
      const realCli = path.join(prefix, "node_modules", "cybercode-cli", "bin", "cli.mjs");
      if (fs.existsSync(realCli)) {
        const content = `@echo off\r\nnode "${realCli}" %*\r\n`;
        fs.writeFileSync(cmdPath, content, "utf-8");
        console.log(`  \u2713 Created cybercode.cmd shim in ${stdNpmDir}`);
      }
    }
  } catch {}

} else if (platform === "linux" || platform === "darwin") {
  try {
    const prefix = execSync("npm config get prefix", { encoding: "utf-8" }).trim();
    const cliPath = path.join(prefix, "bin", "cybercode");
    if (!fs.existsSync("/usr/local/bin/cybercode") && fs.existsSync(cliPath)) {
      try {
        execSync(`ln -sf "${cliPath}" /usr/local/bin/cybercode`);
      } catch {}
    }
  } catch {}
}

process.exit(0);
