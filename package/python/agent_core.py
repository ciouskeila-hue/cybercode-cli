#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent_core — a self-contained minimal autonomous agent.

This module implements the core of an autonomous agent: an LLM client
(OpenAI-compatible, streaming, with function-calling), a ~100-line agent
loop, and 9 atomic tools for system-level control (code execution, file
I/O, web fetching, user interaction, and memory management).

The architecture and design philosophy are inspired by and reference the
GenericAgent project (https://github.com/lsdefine/GenericAgent), which is
licensed under the MIT License. See the LICENSE file and README for full
attribution.

Dependencies: only the Python standard library + `requests` (already a
dependency of most agent setups). No LangChain, no Playwright, no browser
binaries.

Usage:
    from agent_core import Agent
    agent = Agent()
    import threading; threading.Thread(target=agent.run, daemon=True).start()
    dq = agent.put_task("Hello, what can you do?")
    while True:
        item = dq.get()
        if "done" in item: print(item["done"]); break
        if "next" in item: print(item["next"], end="")
"""
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    import requests
except ImportError:
    requests = None  # web tools will degrade gracefully

# ---------------------------------------------------------------------------
# License attribution
# ---------------------------------------------------------------------------
# Portions of this agent core (the agent loop structure, the 9-tool design,
# the memory layering concept, and the system prompt philosophy) are derived
# from GenericAgent by lsdefine, licensed under the MIT License:
#
#   Copyright (c) 2025 lsdefine
#   https://github.com/lsdefine/GenericAgent
#
# See LICENSE for the full MIT text.

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = SCRIPT_DIR
TEMP_DIR = os.path.join(SCRIPT_DIR, "temp")
MEMORY_DIR = os.path.join(SCRIPT_DIR, "memory")
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(MEMORY_DIR, exist_ok=True)

# Ensure memory files exist
_MEM_FILES = {
    "global_mem.txt": "# [Global Memory - L2]\n",
    "global_mem_insight.txt": "# [Global Memory Insight - L1]\nRead global_mem.txt for L2 facts.\nL2: currently empty\nL3: (none yet)\n",
}
for _f, _default in _MEM_FILES.items():
    _p = os.path.join(MEMORY_DIR, _f)
    if not os.path.exists(_p):
        with open(_p, "w", encoding="utf-8") as fh:
            fh.write(_default)

FILE_HINT = "If you need to show files to user, use [FILE:filepath] in your response."

SYSTEM_PROMPT = """# Role: Physical-Level Omnipotent Executor
You have full physical access: file I/O, script execution, web fetching, and system-level intervention. Never deflect with "can't do it" — don't speculate, use tools to probe.
Summarize and reply in the user's language or follow the user's prompt.

## Action Principles
Before each tool call, reason about: current phase, whether the last result met expectations, and next strategy. Include a <summary> in the reply text of each turn.
- Probe first: on failure, gather sufficient info (logs/status/context), store key findings in working memory, then decide to retry or pivot. Ask the user before irreversible operations.
- Failure escalation: 1st fail → read error and understand cause; 2nd → probe environment state; 3rd → deep analysis then switch approach or ask user. Never repeat an action without new information.

## Memory
- L0: Meta rules (this prompt)
- L1: ../memory/global_mem_insight.txt (minimal index)
- L2: ../memory/global_mem.txt (stable facts)
- L3: ../memory/*.md (task SOPs)
- Use update_working_checkpoint for short-term notes during long tasks.
- Use start_long_term_update when a task completes and has lessons worth saving.

## Constitution
1. Execute step by step, control granularity, limit blast radius; request intervention after 3 failures.
2. Check memory before decisions; always use existing SOPs; revisit on repeated failures.
3. Key/secret files: reference only, never read or move.
4. Files under memory/ should be patched (not overwritten) unless creating new ones.
"""

# ---------------------------------------------------------------------------
# Tool schema (OpenAI function-calling format)
# ---------------------------------------------------------------------------
TOOLS_SCHEMA = [
    {"type": "function", "function": {
        "name": "code_run",
        "description": "Code executor. Prefer python. Runs Python scripts or bash/shell commands.",
        "parameters": {"type": "object", "properties": {
            "script": {"type": "string", "description": "The code to run. For python, this is a multi-line script. For shell, a single command."},
            "type": {"type": "string", "enum": ["python", "bash", "shell"], "description": "Code type", "default": "python"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60},
            "cwd": {"type": "string", "description": "Working directory"},
        }, "required": ["script"]},
    }},
    {"type": "function", "function": {
        "name": "file_read",
        "description": "Read file content. Read before modify for latest context and line numbers.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Relative or absolute file path"},
            "start": {"type": "integer", "description": "Start line (1-based)", "default": 1},
            "count": {"type": "integer", "description": "Number of lines to read", "default": 200},
            "show_linenos": {"type": "boolean", "description": "Show line numbers", "default": True},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "file_write",
        "description": "Create/overwrite/append files. Content goes in the 'content' parameter.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path"},
            "content": {"type": "string", "description": "Content to write"},
            "mode": {"type": "string", "enum": ["overwrite", "append", "prepend"], "description": "Write mode", "default": "overwrite"},
        }, "required": ["path", "content"]},
    }},
    {"type": "function", "function": {
        "name": "file_patch",
        "description": "Replace a unique old_content block with new_content. Exact match required. On failure, file_read to recheck.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path"},
            "old_content": {"type": "string", "description": "Original text block to replace (must be unique in the file)"},
            "new_content": {"type": "string", "description": "New content"},
        }, "required": ["path", "old_content", "new_content"]},
    }},
    {"type": "function", "function": {
        "name": "web_scan",
        "description": "Fetch a URL and return simplified text content. Uses HTTP requests (no JavaScript rendering).",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "text_only": {"type": "boolean", "description": "Return plain text only (strip HTML)", "default": True},
        }, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "web_execute_js",
        "description": "Execute JavaScript in a browser. Requires TMWebDriver extension to be set up. Returns setup instructions if not available.",
        "parameters": {"type": "object", "properties": {
            "script": {"type": "string", "description": "JavaScript code to execute"},
            "switch_tab_id": {"type": "string", "description": "Optional tab ID"},
        }, "required": ["script"]},
    }},
    {"type": "function", "function": {
        "name": "ask_user",
        "description": "Interrupt task to ask the user for decisions, extra info, or to resolve blockers.",
        "parameters": {"type": "object", "properties": {
            "question": {"type": "string", "description": "Question for the user"},
            "candidates": {"type": "array", "items": {"type": "string"}, "description": "Optional quick-select choices"},
        }, "required": ["question"]},
    }},
    {"type": "function", "function": {
        "name": "update_working_checkpoint",
        "description": "Short-term working notepad. Auto-injected each turn to prevent info loss in long tasks. Call during early/mid stages.",
        "parameters": {"type": "object", "properties": {
            "key_info": {"type": "string", "description": "Key info to remember (<200 tokens): pitfalls, requirements, findings, file paths, progress, next steps."},
            "related_sop": {"type": "string", "description": "Related SOP names for further reading"},
        }, "required": ["key_info"]},
    }},
    {"type": "function", "function": {
        "name": "start_long_term_update",
        "description": "Start distilling long-term memory. Call when discovering info worth remembering (env facts, user prefs, lessons learned).",
        "parameters": {"type": "object", "properties": {}},
    }},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def smart_format(data, max_str_len=200, omit_str="\n\n[omitted long content]\n\n"):
    if not isinstance(data, str):
        data = str(data)
    if len(data) < max_str_len + len(omit_str) * 2:
        return data
    return f"{data[:max_str_len // 2]}{omit_str}{data[-max_str_len // 2:]}"


def format_error(e):
    exc_type, exc_value, exc_tb = sys.exc_info()
    tb = traceback.extract_tb(exc_tb)
    if tb:
        f = tb[-1]
        return f"{exc_type.__name__}: {exc_value} @ {os.path.basename(f.filename)}:{f.lineno}"
    return f"{exc_type.__name__}: {exc_value}"


def clean_reply(text):
    """Strip internal tags for display."""
    for pat in [r"<thinking>[\s\S]*?</thinking>", r"<summary>[\s\S]*?</summary>",
                r"<tool_use>[\s\S]*?</tool_use>", r"<file_content>[\s\S]*?</file_content>"]:
        text = re.sub(pat, "", text or "", flags=re.DOTALL)
    return re.sub(r"\n{3,}", "\n\n", text).strip() or "..."


def extract_files(text):
    return re.findall(r"\[FILE:([^\]]+)\]", text or "")


def strip_files(text):
    return re.sub(r"\[FILE:[^\]]+\]", "", text or "").strip()


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------
def tool_code_run(script, code_type="python", timeout=60, cwd=None, stop_signal=None):
    """Execute Python or shell code. Yields progress, returns result dict."""
    cwd = cwd or TEMP_DIR
    os.makedirs(cwd, exist_ok=True)
    preview = (script[:80].replace("\n", " ") + "...") if len(script) > 80 else script.strip()
    yield f"[Action] Running {code_type}: {preview}\n"

    if code_type in ("python", "py"):
        tmp = tempfile.NamedTemporaryFile(suffix=".ai.py", delete=False, mode="w", encoding="utf-8", dir=cwd)
        tmp.write(script)
        tmp.close()
        cmd = [sys.executable, "-X", "utf8", "-u", tmp.name]
    elif code_type in ("bash", "shell", "sh"):
        cmd = ["bash", "-c", script]
    else:
        return {"status": "error", "msg": f"Unsupported type: {code_type}"}

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                bufsize=0, cwd=cwd, text=True, encoding="utf-8", errors="replace")
        stdout_lines = []
        start_t = time.time()
        for line in iter(proc.stdout.readline, ""):
            stdout_lines.append(line)
            if time.time() - start_t > timeout or (stop_signal and stop_signal):
                proc.kill()
                stdout_lines.append("\n[Stopped] Timeout or user abort\n")
                break
        proc.wait(timeout=5)
        exit_code = proc.returncode
        stdout_str = "".join(stdout_lines)
        status = "success" if exit_code == 0 else "error"
        icon = "✅" if exit_code == 0 else "❌"
        yield f"[Status] {icon} Exit Code: {exit_code}\n[Stdout]\n{smart_format(stdout_str, max_str_len=8000)}\n"
        return {"status": status, "stdout": smart_format(stdout_str, max_str_len=10000), "exit_code": exit_code}
    except Exception as e:
        return {"status": "error", "msg": str(e)}
    finally:
        if code_type == "python" and "tmp" in dir() and os.path.exists(tmp.name):
            os.remove(tmp.name)


def tool_file_read(path, start=1, count=200, show_linenos=True):
    """Read file content with optional line numbers."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        end = min(start - 1 + count, len(lines))
        result_lines = lines[start - 1:end]
        if show_linenos:
            result = f"[FILE] {len(lines)} lines | showing {start}-{end}\n"
            result += "\n".join(f"{start + i}|{line.rstrip()}" for i, line in enumerate(result_lines))
        else:
            result = "".join(result_lines)
        remaining = len(lines) - end
        if remaining > 0:
            result += f"\n\n[{remaining} more lines below]"
        return smart_format(result, max_str_len=15000)
    except FileNotFoundError:
        return f"Error: File not found: {path}"
    except Exception as e:
        return f"Error: {e}"


def tool_file_write(path, content, mode="overwrite"):
    """Write content to file."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        if mode == "prepend":
            old = open(path, "r", encoding="utf-8").read() if os.path.exists(path) else ""
            with open(path, "w", encoding="utf-8") as f:
                f.write(content + old)
        elif mode == "append":
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        return {"status": "success", "writed_bytes": len(content)}
    except Exception as e:
        return {"status": "error", "msg": str(e)}


def tool_file_patch(path, old_content, new_content):
    """Replace unique old_content with new_content in file."""
    try:
        if not os.path.exists(path):
            return {"status": "error", "msg": "File not found"}
        with open(path, "r", encoding="utf-8") as f:
            full = f.read()
        if not old_content:
            return {"status": "error", "msg": "old_content is empty"}
        count = full.count(old_content)
        if count == 0:
            return {"status": "error", "msg": "old_content not found. Use file_read to check current content."}
        if count > 1:
            return {"status": "error", "msg": f"Found {count} matches. Provide a longer, more specific old_content."}
        updated = full.replace(old_content, new_content)
        with open(path, "w", encoding="utf-8") as f:
            f.write(updated)
        return {"status": "success", "msg": "File patched successfully"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}


def tool_web_scan(url, text_only=True):
    """Fetch a URL and return text content."""
    if requests is None:
        return {"status": "error", "msg": "requests library not installed. Run: pip install requests"}
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=30, verify=False)
        content_type = resp.headers.get("content-type", "")
        if text_only and "html" in content_type:
            # Simple HTML to text
            import html.parser
            class _Stripper(html.parser.HTMLParser):
                def __init__(self):
                    super().__init__(); self.text = []
                def handle_data(self, d): self.text.append(d)
                def get_text(self): return " ".join(self.text)
            s = _Stripper()
            s.feed(resp.text)
            text = re.sub(r"\s+", " ", s.get_text()).strip()
            return {"status": "success", "url": str(resp.url), "content": smart_format(text, max_str_len=30000)}
        return {"status": "success", "url": str(resp.url), "content": smart_format(resp.text, max_str_len=30000)}
    except Exception as e:
        return {"status": "error", "msg": format_error(e)}


def tool_web_execute_js(script, switch_tab_id=None):
    """Execute JS in browser. Requires TMWebDriver (not bundled)."""
    return {"status": "error", "msg": "Browser JS execution requires TMWebDriver. To set up: install the Chrome extension from the GenericAgent repo's assets/tmwd_cdp_bridge/ directory, or use web_scan for basic HTTP fetching."}


def tool_ask_user(question, candidates=None):
    """Return an interrupt signal for human intervention."""
    return {"status": "INTERRUPT", "intent": "HUMAN_INTERVENTION",
            "data": {"question": question, "candidates": candidates or []}}


# ---------------------------------------------------------------------------
# Step outcome + handler
# ---------------------------------------------------------------------------
@dataclass
class StepOutcome:
    data: Any
    next_prompt: Optional[str] = None
    should_exit: bool = False


class AgentHandler:
    """Dispatches tool calls and manages working memory + history."""

    def __init__(self, parent, last_history=None, cwd=TEMP_DIR):
        self.parent = parent
        self.working = {}
        self.cwd = cwd
        self.current_turn = 0
        self.history_info = last_history if last_history else []
        self.code_stop_signal = []
        self.max_turns = 180

    def _get_abs_path(self, path):
        if not path:
            return ""
        if os.path.isabs(path):
            return path
        return os.path.abspath(os.path.join(self.cwd, path))

    def _get_anchor_prompt(self):
        """Build the working-memory prompt injected each turn."""
        h = self.history_info
        W = 30
        h_str = "\n".join(h[-W:])
        prompt = f"\n### [WORKING MEMORY]\n<history>\n{h_str}\n</history>"
        prompt += f"\nCurrent turn: {self.current_turn}\n"
        if self.working.get("key_info"):
            prompt += f"\n<key_info>{self.working.get('key_info')}</key_info>"
        return prompt

    def dispatch(self, tool_name, args, response, index=0, tool_num=1):
        """Dispatch a tool call. Yields progress text, returns StepOutcome."""
        method = getattr(self, f"do_{tool_name}", None)
        if method is None:
            yield f"Unknown tool: {tool_name}\n"
            return StepOutcome(None, next_prompt=f"Unknown tool {tool_name}")
        args["_index"] = index
        args["_tool_num"] = tool_num
        ret = method(args, response)
        # Handle both generators and direct returns
        if hasattr(ret, "__iter__") and not isinstance(ret, (str, dict, list)):
            return (yield from ret)
        return ret

    def turn_end_callback(self, response, tool_calls, tool_results, turn, next_prompt, exit_reason):
        """Extract summary and add periodic reminders."""
        content = getattr(response, "content", "") or ""
        rsumm = re.search(r"<summary>(.*?)</summary>", content, re.DOTALL)
        if rsumm:
            summary = rsumm.group(1).strip()
        else:
            tc = tool_calls[0]
            tool_name, targs = tc["tool_name"], tc["args"]
            clean_args = {k: v for k, v in targs.items() if not k.startswith("_")}
            summary = f"{tool_name}, args: {clean_args}"
            if tool_name == "no_tool":
                summary = "Responded directly"
        summary = smart_format(summary.replace("\n", ""), max_str_len=80)
        self.history_info.append(f"[Agent] {summary}")

        if turn % 7 == 0:
            next_prompt += f"\n\n[SYSTEM] Turn {turn}. Call update_working_checkpoint to save key context."
        return next_prompt

    # ---- tool implementations ----
    def do_code_run(self, args, response):
        code = args.get("script") or args.get("code")
        if not code:
            return StepOutcome("[Error] No code provided.", next_prompt="\n")
        code_type = args.get("type", "python")
        timeout = int(args.get("timeout", 60))
        cwd = self._get_abs_path(args.get("cwd", "./"))
        result = yield from tool_code_run(code, code_type, timeout, cwd, self.code_stop_signal)
        return StepOutcome(result, next_prompt=self._get_anchor_prompt())

    def do_file_read(self, args, response):
        path = self._get_abs_path(args.get("path", ""))
        yield f"[Action] Reading: {path}\n"
        result = tool_file_read(path, args.get("start", 1), args.get("count", 200), args.get("show_linenos", True))
        return StepOutcome(smart_format(result, max_str_len=15000), next_prompt=self._get_anchor_prompt())

    def do_file_write(self, args, response):
        path = self._get_abs_path(args.get("path", ""))
        content = args.get("content", "")
        mode = args.get("mode", "overwrite")
        yield f"[Action] Writing {mode}: {os.path.basename(path)}\n"
        result = tool_file_write(path, content, mode)
        yield f"[Status] {result}\n"
        return StepOutcome(result, next_prompt=self._get_anchor_prompt())

    def do_file_patch(self, args, response):
        path = self._get_abs_path(args.get("path", ""))
        yield f"[Action] Patching: {path}\n"
        result = tool_file_patch(path, args.get("old_content", ""), args.get("new_content", ""))
        yield f"{result}\n"
        return StepOutcome(result, next_prompt=self._get_anchor_prompt())

    def do_web_scan(self, args, response):
        url = args.get("url", "")
        yield f"[Action] Fetching: {url}\n"
        result = tool_web_scan(url, args.get("text_only", True))
        yield f"[Result] {smart_format(str(result), max_str_len=500)}\n"
        return StepOutcome(smart_format(json.dumps(result, ensure_ascii=False), max_str_len=8000),
                           next_prompt=self._get_anchor_prompt())

    def do_web_execute_js(self, args, response):
        result = tool_web_execute_js(args.get("script", ""), args.get("switch_tab_id"))
        yield f"[Result] {result}\n"
        return StepOutcome(result, next_prompt=self._get_anchor_prompt())

    def do_ask_user(self, args, response):
        question = args.get("question", "Please provide input:")
        candidates = args.get("candidates", [])
        result = tool_ask_user(question, candidates)
        yield f"Waiting for your answer...\n"
        return StepOutcome(result, next_prompt="", should_exit=True)

    def do_update_working_checkpoint(self, args, response):
        key_info = args.get("key_info", "")
        related_sop = args.get("related_sop", "")
        if key_info:
            self.working["key_info"] = key_info
        if related_sop:
            self.working["related_sop"] = related_sop
        yield f"[Info] Updated working memory.\n"
        return StepOutcome({"result": "working key_info updated"}, next_prompt=self._get_anchor_prompt())

    def do_start_long_term_update(self, args, response):
        prompt = """### [Distill Experience]
Extract verified, long-term-useful info from the recent task:
- **Environment facts** (paths, configs) → file_patch into memory/global_mem.txt
- **Task experience** (pitfalls, key steps) → write a new SOP .md in memory/

Only extract verified, reusable info. Skip ephemeral data, unverified guesses, or common knowledge.
Use file_read to check existing memory first, then file_patch for minimal updates.
"""
        yield "[Info] Starting long-term memory distillation.\n"
        insight = ""
        insight_path = os.path.join(MEMORY_DIR, "global_mem_insight.txt")
        if os.path.exists(insight_path):
            with open(insight_path, "r", encoding="utf-8") as f:
                insight = f.read()
        return StepOutcome(f"Current L1 insight:\n{insight}", next_prompt=prompt)

    def do_no_tool(self, args, response):
        """Called when the LLM doesn't invoke any tool — signals task completion."""
        content = getattr(response, "content", "") or ""
        if not content.strip():
            yield "[Warn] Empty response. Retrying...\n"
            return StepOutcome({}, next_prompt="[System] Blank response, please respond with content or a tool call.")
        return StepOutcome(response, next_prompt=None)


# ---------------------------------------------------------------------------
# LLM Client (OpenAI-compatible, streaming, with function calling)
# ---------------------------------------------------------------------------
class LLMResponse:
    """Parsed LLM response."""
    def __init__(self, content="", tool_calls=None, raw=None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.raw = raw or ""


class MockToolCall:
    def __init__(self, name, args, id=""):
        self.id = id
        self.function = type("F", (), {"name": name, "arguments": json.dumps(args, ensure_ascii=False)})()


class LLMClient:
    """OpenAI-compatible streaming LLM client with function-calling support.

    Works with OpenAI, DeepSeek, Kimi/Moonshot, local models (Ollama, vLLM),
    and any endpoint that implements /v1/chat/completions with tools.
    """

    def __init__(self, cfg):
        self.api_key = cfg.get("apikey", "")
        self.api_base = cfg.get("apibase", "https://api.openai.com").rstrip("/")
        self.model = cfg.get("model", "gpt-4o")
        self.name = cfg.get("name", self.model)
        self.context_win = cfg.get("context_win", 30000)
        self.temperature = cfg.get("temperature", 1)
        self.max_tokens = cfg.get("max_tokens")
        self.stream = cfg.get("stream", True)
        self.connect_timeout = cfg.get("timeout", 10)
        self.read_timeout = cfg.get("read_timeout", 240)
        self.max_retries = cfg.get("max_retries", 3)
        self.history = []
        self.system = ""
        self.tools = None
        self._lock = threading.Lock()
        self.log_path = None

    def _make_url(self):
        base = self.api_base.rstrip("/")
        if "/v1" in base:
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def _build_messages(self, messages):
        """Convert internal message format to OpenAI format."""
        msgs = []
        if self.system:
            msgs.append({"role": "system", "content": self.system})
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            tool_results = m.get("tool_results", [])
            if isinstance(content, list):
                # Extract text from content blocks
                texts = []
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "text":
                        texts.append(b.get("text", ""))
                    elif isinstance(b, str):
                        texts.append(b)
                content = "\n".join(texts)
            if tool_results:
                for tr in tool_results:
                    msgs.append({"role": "tool", "tool_call_id": tr.get("tool_use_id", ""),
                                 "content": tr.get("content", "")})
            if content:
                msgs.append({"role": role, "content": str(content)})
        return msgs

    def chat(self, messages, tools=None):
        """Stream LLM response. Yields text chunks, returns LLMResponse."""
        if requests is None:
            raise RuntimeError("requests library required. Install: pip install requests")

        self.tools = tools
        oai_messages = self._build_messages(messages)
        url = self._make_url()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if self.stream else "application/json",
        }
        payload = {"model": self.model, "messages": oai_messages, "stream": self.stream}
        if self.temperature != 1:
            payload["temperature"] = self.temperature
        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens
        if tools:
            payload["tools"] = tools
        if self.stream:
            payload["stream_options"] = {"include_usage": True}

        # Retry logic
        retryable = {408, 409, 425, 429, 500, 502, 503, 504}
        for attempt in range(self.max_retries + 1):
            try:
                with requests.post(url, headers=headers, json=payload, stream=self.stream,
                                   timeout=(self.connect_timeout, self.read_timeout)) as resp:
                    if resp.status_code >= 400:
                        body = resp.text[:500]
                        if resp.status_code in retryable and attempt < self.max_retries:
                            delay = min(30, 1.5 * (2 ** attempt))
                            print(f"[LLM Retry] HTTP {resp.status_code}, retry in {delay:.1f}s")
                            time.sleep(delay)
                            continue
                        err_text = f"!!!Error: HTTP {resp.status_code}: {body}"
                        yield err_text
                        return LLMResponse(content=err_text)

                    if self.stream:
                        return (yield from self._parse_stream(resp))
                    else:
                        return self._parse_json(resp.json())
            except (requests.Timeout, requests.ConnectionError) as e:
                err = f"!!!Error: {type(e).__name__}: {e}"
                if attempt < self.max_retries:
                    delay = min(30, 1.5 * (2 ** attempt))
                    print(f"[LLM Retry] {type(e).__name__}, retry in {delay:.1f}s")
                    yield err
                    time.sleep(delay)
                    continue
                yield err
                return LLMResponse(content=err)
        return LLMResponse(content="!!!Error: Max retries exceeded")

    def _parse_stream(self, resp):
        """Parse OpenAI SSE stream. Yields text chunks, returns LLMResponse."""
        content_text = ""
        tc_buf = {}  # index -> {id, name, args}

        for line in resp.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else line
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                evt = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            choices = evt.get("choices") or [{}]
            ch = choices[0]
            delta = ch.get("delta") or {}

            # Reasoning content (some providers)
            if rc := delta.get("reasoning_content") or delta.get("reasoning", ""):
                pass  # silently consume reasoning

            if delta.get("content"):
                text = delta["content"]
                content_text += text
                yield text

            for tc in (delta.get("tool_calls") or []):
                idx = tc.get("index", 0)
                if idx not in tc_buf:
                    tc_buf[idx] = {"id": "", "name": "", "args": ""}
                func = tc.get("function", {})
                if func.get("name"):
                    tc_buf[idx]["name"] = func["name"]
                if func.get("arguments"):
                    tc_buf[idx]["args"] += func["arguments"]
                if tc.get("id") and not tc_buf[idx]["id"]:
                    tc_buf[idx]["id"] = tc["id"]

        # Build tool calls
        tool_calls = []
        for idx in sorted(tc_buf):
            tc = tc_buf[idx]
            try:
                args = json.loads(tc["args"]) if tc["args"] else {}
            except json.JSONDecodeError:
                args = {"_raw": tc["args"]}
            tool_calls.append(MockToolCall(tc["name"], args, id=tc["id"]))

        return LLMResponse(content=content_text, tool_calls=tool_calls)

    def _parse_json(self, data):
        """Parse non-streaming JSON response."""
        msg = (data.get("choices") or [{}])[0].get("message", {})
        content = msg.get("content", "") or ""
        tool_calls = []
        for tc in (msg.get("tool_calls") or []):
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments", "")) if fn.get("arguments") else {}
            except json.JSONDecodeError:
                args = {"_raw": fn.get("arguments", "")}
            tool_calls.append(MockToolCall(fn.get("name", ""), args, id=tc.get("id", "")))
        return LLMResponse(content=content, tool_calls=tool_calls)


# ---------------------------------------------------------------------------
# Agent Loop
# ---------------------------------------------------------------------------
def agent_loop(client, system_prompt, user_input, handler, tools_schema,
               max_turns=180, verbose=True):
    """The core agent loop: LLM → tool dispatch → next prompt → repeat.

    Yields text chunks for streaming. Returns when the task is done.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": [{"type": "text", "text": user_input}]},
    ]
    handler.max_turns = max_turns
    turn = 0

    while turn < handler.max_turns:
        turn += 1
        yield f"\n\n**LLM Running (Turn {turn}) ...**\n\n"

        # Call LLM
        client.system = system_prompt
        try:
            response = yield from client.chat(messages, tools=tools_schema)
        except Exception as e:
            yield f"\n[Error] LLM call failed: {format_error(e)}\n"
            break

        if response is None:
            response = LLMResponse(content="!!!Error: No response")

        # Parse tool calls
        if response.tool_calls:
            tool_calls = [{"tool_name": tc.function.name,
                           "args": json.loads(tc.function.arguments) if tc.function.arguments else {},
                           "id": tc.id} for tc in response.tool_calls]
        else:
            tool_calls = [{"tool_name": "no_tool", "args": {}}]

        tool_results = []
        next_prompts = set()
        exit_reason = {}

        for ii, tc in enumerate(tool_calls):
            tool_name, args, tid = tc["tool_name"], tc["args"], tc.get("id", "")
            if tool_name != "no_tool":
                yield f"🛠️ Tool: `{tool_name}`  📥 args:\n````text\n{json.dumps(args, indent=2, ensure_ascii=False)}\n````\n"

            handler.current_turn = turn
            gen = handler.dispatch(tool_name, args, response, index=ii, tool_num=len(tool_calls))
            try:
                v = next(gen)
                if verbose:
                    yield "`````\n"
                outcome = (yield from gen) if verbose else (yield from gen)
                if verbose:
                    yield "`````\n"
            except StopIteration as e:
                outcome = e.value

            if outcome is None:
                outcome = StepOutcome(None, next_prompt="\n")

            if outcome.should_exit:
                exit_reason = {"result": "EXITED", "data": outcome.data}
                break
            if not outcome.next_prompt:
                exit_reason = {"result": "CURRENT_TASK_DONE", "data": outcome.data}
                break

            if outcome.data is not None and tool_name != "no_tool":
                datastr = json.dumps(outcome.data, ensure_ascii=False, default=str) if isinstance(outcome.data, (dict, list)) else str(outcome.data)
                tool_results.append({"tool_use_id": tid, "content": datastr})
            next_prompts.add(outcome.next_prompt)

        if not next_prompts or exit_reason:
            break

        next_prompt = handler.turn_end_callback(response, tool_calls, tool_results, turn,
                                                "\n".join(next_prompts), exit_reason)
        messages = [{"role": "user", "content": next_prompt, "tool_results": tool_results}]

    return exit_reason or {"result": "MAX_TURNS_EXCEEDED"}


# ---------------------------------------------------------------------------
# Config loading (mykey.py / mykey.json)
# ---------------------------------------------------------------------------
def load_mykeys():
    """Load LLM configs from mykey.py or mykey.json.

    Format (mykey.py):
        llm1 = {"apikey": "sk-...", "apibase": "https://api.openai.com", "model": "gpt-4o", "name": "GPT-4o"}
        llm2 = {"apikey": "sk-...", "apibase": "https://api.deepseek.com", "model": "deepseek-chat", "name": "DeepSeek"}

    Format (mykey.json):
        {"llm1": {"apikey": "...", "apibase": "...", "model": "...", "name": "..."}}
    """
    # Try mykey.py
    for search_dir in [SCRIPT_DIR, os.getcwd()]:
        mykey_py = os.path.join(search_dir, "mykey.py")
        if os.path.exists(mykey_py):
            import importlib.util
            spec = importlib.util.spec_from_file_location("mykey", mykey_py)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return {k: v for k, v in vars(mod).items()
                    if not k.startswith("_") and isinstance(v, dict) and "apikey" in v}

    # Try mykey.json
    for search_dir in [SCRIPT_DIR, os.getcwd()]:
        mykey_json = os.path.join(search_dir, "mykey.json")
        if os.path.exists(mykey_json):
            with open(mykey_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {k: v for k, v in data.items()
                    if isinstance(v, dict) and "apikey" in v}

    return {}


def get_global_memory():
    """Read L1 + L2 memory for the system prompt."""
    prompt = f"\ncwd = {TEMP_DIR} (./)\n"
    prompt += f"\n[Memory] ({MEMORY_DIR})\n"
    insight_path = os.path.join(MEMORY_DIR, "global_mem_insight.txt")
    if os.path.exists(insight_path):
        with open(insight_path, "r", encoding="utf-8", errors="replace") as f:
            prompt += f"L1 Insight:\n{f.read()}\n"
    return prompt


# ---------------------------------------------------------------------------
# Agent (the main class users interact with)
# ---------------------------------------------------------------------------
class Agent:
    """The main agent. Put tasks on a queue, drain the output queue for results.

    Usage:
        agent = Agent()
        threading.Thread(target=agent.run, daemon=True).start()
        dq = agent.put_task("Hello!")
        while True:
            item = dq.get()
            if "done" in item: print(item["done"]); break
            if "next" in item: print(item["next"], end="")
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.history = []
        self.handler = None
        self.task_queue = queue.Queue()
        self.is_running = False
        self.stop_sig = False
        self.llm_no = 0
        self.inc_out = False
        self.verbose = True
        self.log_path = ""
        self.llmclient = None
        self._llm_clients = []
        self._llm_names = []
        self._load_llms()

    def _load_llms(self):
        """Initialize LLM clients from mykey config."""
        mykeys = load_mykeys()
        if not mykeys:
            print("[agent_core] WARNING: no LLM config found. Create mykey.py or mykey.json.")
            return
        self._llm_clients = []
        self._llm_names = []
        for k, cfg in mykeys.items():
            try:
                client = LLMClient(cfg)
                self._llm_clients.append(client)
                self._llm_names.append(cfg.get("name", cfg.get("model", k)))
            except Exception as e:
                print(f"[agent_core] Failed to init LLM '{k}': {e}")
        if self._llm_clients:
            self.llmclient = self._llm_clients[0]

    def list_llms(self):
        """Return [(index, name, is_active), ...]"""
        return [(i, name, i == self.llm_no) for i, name in enumerate(self._llm_names)]

    def is_configured(self):
        """True only when at least one LLM client has a real (non-placeholder) API key."""
        for c in self._llm_clients:
            key = getattr(c, "api_key", "") or ""
            if key and "YOUR-" not in key and not key.endswith("..."):
                return True
        return False

    def get_llm_name(self, client=None):
        if client is None:
            client = self.llmclient
        if client is None:
            return "not configured"
        return client.name

    def next_llm(self, n=-1):
        """Switch LLM. n=-1 for next, or pass an explicit index."""
        if not self._llm_clients:
            raise Exception("No LLM clients available")
        self.llm_no = ((self.llm_no + 1) if n < 0 else n) % len(self._llm_clients)
        self.llmclient = self._llm_clients[self.llm_no]
        return self.llm_no

    def abort(self):
        if not self.is_running:
            return
        print("Aborting current task...")
        self.stop_sig = True
        if self.handler is not None:
            self.handler.code_stop_signal.append(1)

    def put_task(self, query, source="user", images=None):
        """Submit a task. Returns an output queue to drain."""
        display_queue = queue.Queue()
        self.task_queue.put({"query": query, "source": source, "images": images or [], "output": display_queue})
        return display_queue

    def run(self):
        """Main agent loop (run in a daemon thread)."""
        while True:
            task = self.task_queue.get()
            if isinstance(task, str):
                break
            raw_query, source, display_queue = task["query"], task["source"], task["output"]
            self.is_running = True
            self.stop_sig = False

            # Truncate very long prompts to a file
            if len(raw_query) > 2000:
                task_file = os.path.join(TEMP_DIR, f"user_prompt_{int(time.time())}.md")
                with open(task_file, "w", encoding="utf-8") as f:
                    f.write(raw_query)
                raw_query = f"Long user prompt saved to {task_file}. Read and execute it."

            rquery = raw_query.replace("\n", " ")[:200]
            self.history.append(f"[USER]: {rquery}")

            # Build system prompt
            sys_prompt = SYSTEM_PROMPT + f"\nToday: {time.strftime('%Y-%m-%d %a')}\n" + get_global_memory()

            # Create handler
            handler = AgentHandler(self, self.history, TEMP_DIR)
            if self.handler and "key_info" in self.handler.working:
                handler.working["key_info"] = self.handler.working.get("key_info", "")
            self.handler = handler

            # Set log path
            import random
            logid = f"{(time.time_ns() + random.randrange(1_000_000)) % 1_000_000:06d}"
            self.log_path = os.path.join(TEMP_DIR, f"model_responses/model_responses_{logid}.txt")
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            if self.llmclient:
                self.llmclient.log_path = self.log_path

            # Run the agent loop
            try:
                full_resp = ""
                last_pos = 0
                curr_turn = 0
                gen = agent_loop(self.llmclient, sys_prompt, raw_query, handler,
                                 TOOLS_SCHEMA, max_turns=180, verbose=self.verbose)
                for chunk in gen:
                    if self.stop_sig:
                        break
                    if isinstance(chunk, dict) and "turn" in chunk:
                        curr_turn = chunk["turn"]
                        continue
                    full_resp += chunk
                    if len(full_resp) - last_pos > 30 or "LLM Running" in chunk:
                        display_queue.put({
                            "next": full_resp[last_pos:] if self.inc_out else full_resp,
                            "source": source, "turn": curr_turn,
                        })
                        last_pos = len(full_resp)
                if self.inc_out and last_pos < len(full_resp):
                    display_queue.put({"next": full_resp[last_pos:], "source": source, "turn": curr_turn})
                display_queue.put({"done": full_resp, "source": source, "turn": curr_turn})
                self.history = handler.history_info
            except Exception as e:
                err = format_error(e)
                print(f"[agent_core] Error: {err}")
                display_queue.put({"done": full_resp + f"\n```\n{err}\n```", "source": source})
            finally:
                if self.stop_sig:
                    print("[agent_core] Task aborted by user.")
                self.is_running = self.stop_sig = False
                self.task_queue.task_done()
                if self.handler is not None:
                    self.handler.code_stop_signal.append(1)
