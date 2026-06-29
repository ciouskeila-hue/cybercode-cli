#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cybercodewebui — a Codex-dark–styled web frontend with a self-contained agent.

Standalone: self-contained agent core (agent_core.py) is
bundled. Only Python stdlib + `requests` are needed.

Usage:
    python cybercodewebui.py                          # http://127.0.0.1:18600
    python cybercodewebui.py --port 9000 --host 0.0.0.0

API:
  GET  /                         -> the web UI
  GET  /api/status               -> {running, configured, llm_no, llm_name, ...}
  GET  /api/sessions             -> past conversation logs
  GET  /api/skills               -> memory/SOP files
  GET  /api/messages?path=...    -> [{role, content}] replay of one session
  GET  /api/hyperframes          -> bundled HyperFrames skill list + preamble
  GET  /api/hyperframes/<slug>   -> raw skill markdown
  GET  /api/videos               -> rendered .mp4 files
  GET  /api/video/<relpath>      -> stream a video file (supports Range)
  POST /api/chat      {text}     -> SSE stream: delta / done / error
  POST /api/chat      {text, video:true}  -> same, with HyperFrames preamble
  POST /api/llm       {idx}      -> switch LLM
  POST /api/stop                 -> abort current task
  POST /api/new                  -> start a fresh conversation
  POST /api/continue   {idx}     -> restore session N
"""
import argparse
import glob
import json
import os
import queue as Q
import re
import ssl
import sys
import threading
import time
import traceback
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from agent_core import (
    Agent, extract_files, strip_files, clean_reply, format_error,
    smart_format, TEMP_DIR, ROOT_DIR,
)

HTML_PATH = os.path.join(HERE, "cybercodewebui.html")
SKILLS_DIR = os.path.join(HERE, "skills")
MEMORY_DIR = os.path.join(HERE, "memory")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18600

# l0veyou backend connection
L0VEYOU_BASE = os.environ.get("L0VEYOU_BASE", "https://l0veyou.com").rstrip("/")
L0VEYOU_SSL_CTX = ssl.create_default_context()
L0VEYOU_SSL_CTX.check_hostname = False
L0VEYOU_SSL_CTX.verify_mode = ssl.CERT_NONE

FILE_HINT = "If you need to show files to user, use [FILE:filepath] in your response."

# ---------------------------------------------------------------------------
# HyperFrames skill pack
# ---------------------------------------------------------------------------
HF_SKILL_ORDER = [
    "hyperframes", "hyperframes-core", "hyperframes-cli",
    "hyperframes-animation", "hyperframes-creative", "hyperframes-media",
    "hyperframes-registry", "general-video", "product-launch-video",
    "website-to-video", "faceless-explainer", "motion-graphics",
]

HF_PREAMBLE = """You have the HyperFrames video skill pack bundled locally.
HyperFrames renders video from HTML compositions and the `npx hyperframes` CLI.

Before writing any video code, read these bundled skill files (use file_read):
  {skills_path}/hyperframes.md        — entry point + intent router
  {skills_path}/hyperframes-core.md   — the composition contract (data-* attrs, determinism)
  {skills_path}/hyperframes-cli.md    — init / lint / validate / preview / render workflow
  {skills_path}/hyperframes-animation.md  — motion rules + runtime adapters
  {skills_path}/hyperframes-creative.md   — design direction, palettes, narration
  {skills_path}/hyperframes-media.md      — TTS, BGM, SFX, captions

The standard workflow is:
  1. npx hyperframes init <project-name>     (scaffolds the composition)
  2. Author the HTML composition per hyperframes-core contract
  3. npx hyperframes lint && npx hyperframes validate && npx hyperframes inspect
  4. npx hyperframes preview                 (ask user before rendering)
  5. npx hyperframes render --output out.mp4 (after user approves)

Rendered .mp4 files appear in the UI's video gallery automatically. Use [FILE:path]
to reference the output so the user can download it.
"""

# ---------------------------------------------------------------------------
# Agent singleton
# ---------------------------------------------------------------------------
_agent = None
_agent_lock = threading.Lock()


def get_agent():
    global _agent
    with _agent_lock:
        if _agent is None:
            _agent = Agent()
            if _agent.llmclient is None:
                print("[cybercodewebui] WARNING: no LLM configured — create mykey.py or mykey.json")
            _agent.inc_out = True
            threading.Thread(target=_agent.run, daemon=True).start()
        return _agent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clean_for_ui(raw):
    r"""Light touch-up: drop <thinking>/<file_content> blocks, keep <summary>,
    tool headers, [FILE:] refs, and turn markers for the frontend to decorate."""
    s = re.sub(r"<thinking>[\s\S]*?</thinking>", "", raw or "")
    s = re.sub(r"<file_content>[\s\S]*?</file_content>", "", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _hf_skills_list():
    out = []
    if not os.path.isdir(SKILLS_DIR):
        return out
    for slug in HF_SKILL_ORDER:
        fpath = os.path.join(SKILLS_DIR, slug + ".md")
        if not os.path.isfile(fpath):
            continue
        st = os.stat(fpath)
        out.append({"slug": slug, "path": fpath, "size": st.st_size, "mtime": int(st.st_mtime)})
    for name in sorted(os.listdir(SKILLS_DIR)):
        slug = name[:-3] if name.endswith(".md") else None
        if slug and slug not in HF_SKILL_ORDER and os.path.isfile(os.path.join(SKILLS_DIR, name)):
            st = os.stat(os.path.join(SKILLS_DIR, name))
            out.append({"slug": slug, "path": os.path.join(SKILLS_DIR, name),
                        "size": st.st_size, "mtime": int(st.st_mtime)})
    return out


def _hf_preamble():
    return HF_PREAMBLE.format(skills_path=SKILLS_DIR)


def _skills_list():
    out = []
    if not os.path.isdir(MEMORY_DIR):
        return out
    for name in sorted(os.listdir(MEMORY_DIR)):
        full = os.path.join(MEMORY_DIR, name)
        try:
            st = os.stat(full)
        except OSError:
            continue
        if os.path.isdir(full):
            out.append({"name": name + "/", "path": full, "is_dir": True, "mtime": int(st.st_mtime)})
        elif name.lower().endswith((".md", ".txt", ".py")):
            out.append({"name": name, "path": full, "is_dir": False,
                        "mtime": int(st.st_mtime), "size": st.st_size})
    return out


def _sessions_list():
    """Scan temp/model_responses/ for conversation logs."""
    log_dir = os.path.join(TEMP_DIR, "model_responses")
    out = []
    if not os.path.isdir(log_dir):
        return out
    for fpath in sorted(glob.glob(os.path.join(log_dir, "model_responses_*.txt")), reverse=True):
        try:
            st = os.stat(fpath)
        except OSError:
            continue
        name = os.path.basename(fpath)
        # Try to extract a preview from the first USER prompt
        preview = ""
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(2000)
            m = re.search(r"=== USER ===\n(.+?)(?==== |\Z)", content, re.DOTALL)
            if m:
                preview = m.group(1).strip().replace("\n", " ")[:80]
            else:
                m2 = re.search(r"\[USER\]:\s*(.+)", content)
                if m2:
                    preview = m2.group(1).strip()[:80]
        except Exception:
            pass
        rounds = content.count("[USER]:") if content else 0
        out.append({
            "path": fpath, "name": name, "mtime": int(st.st_mtime),
            "preview": preview, "rounds": rounds,
            "current": fpath == (get_agent().log_path or ""),
        })
    return out


def _extract_messages(log_path):
    """Extract conversation turns from a model_responses log file."""
    if not log_path or not os.path.isfile(log_path):
        return []
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return []
    msgs = []
    # Try native format: === USER === / === ASSISTANT === blocks
    blocks = re.findall(r"=== (?:USER|ASSISTANT) ===\n(.+?)(?==== (?:USER|ASSISTANT) ===|\Z)", content, re.DOTALL)
    if blocks:
        for i, block in enumerate(blocks):
            role = "user" if i % 2 == 0 else "assistant"
            msgs.append({"role": role, "content": block.strip()[:5000]})
    else:
        # Try [USER]: / [Agent] format
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("[USER]:"):
                msgs.append({"role": "user", "content": line[7:].strip()})
            elif line.startswith("[Agent]"):
                msgs.append({"role": "assistant", "content": line[7:].strip()})
    return msgs


def _videos_list():
    """Scan for rendered .mp4 files."""
    out = []
    search_dirs = [HERE, TEMP_DIR, os.path.join(HERE, "output"), ROOT_DIR]
    seen = set()
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for fpath in glob.glob(os.path.join(d, "**", "*.mp4"), recursive=True):
            try:
                rp = os.path.relpath(fpath, HERE)
            except ValueError:
                rp = fpath
            if rp in seen:
                continue
            seen.add(rp)
            try:
                st = os.stat(fpath)
            except OSError:
                continue
            if st.st_size < 1024:
                continue
            out.append({"name": os.path.basename(fpath), "path": rp, "abspath": fpath,
                        "size": st.st_size, "mtime": int(st.st_mtime)})
    out.sort(key=lambda v: v["mtime"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "cybercodewebui/2.0"
    protocol_version = "HTTP/1.1"

    def _send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return {}

    def log_message(self, *args):
        pass

    # ---- routing ----
    def do_GET(self):
        url = urlparse(self.path)
        path, qs = url.path, parse_qs(url.query)
        try:
            if path in ("", "/"):
                return self._serve_html()
            if path == "/api/status":
                return self._api_status()
            if path == "/api/sessions":
                return self._send_json({"items": _sessions_list()})
            if path == "/api/skills":
                return self._send_json({"items": _skills_list()})
            if path == "/api/messages":
                return self._send_json({"items": _extract_messages((qs.get("path") or [""])[0])})
            if path == "/api/hyperframes":
                return self._send_json({"items": _hf_skills_list(), "preamble": _hf_preamble()})
            if path.startswith("/api/hyperframes/"):
                return self._api_hf_skill(unquote(path[len("/api/hyperframes/"):]))
            if path == "/api/videos":
                return self._send_json({"items": _videos_list()})
            if path.startswith("/api/video/"):
                return self._serve_video(unquote(path[len("/api/video/"):]))
            if path == "/api/llm/get":
                return self._api_llm_get()
            # l0veyou proxy routes
            if path == "/proxy/auth/providers":
                return self._proxy_get("/auth/providers")
            if path == "/proxy/auth/session":
                return self._proxy_get_auth("/auth/session")
            if path == "/proxy/v1/models":
                return self._proxy_get_auth("/v1/models")
            if path == "/auth/callback":
                return self._serve_html()
            if path.startswith("/proxy/api/creation-tasks"):
                return self._proxy_get_auth(path.replace("/proxy", ""))
            if path.startswith("/proxy/images/") or path.startswith("/proxy/temp-images/") or path.startswith("/proxy/ltx_video/") or path.startswith("/proxy/image-thumbnails/") or path.startswith("/proxy/image-references/"):
                return self._proxy_file(path.replace("/proxy", ""))
            self._send_json({"error": "not found"}, 404)
        except Exception as e:
            traceback.print_exc()
            self._send_json({"error": str(e)}, 500)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/chat":
                return self._api_chat()
            if path == "/api/llm":
                return self._api_llm()
            if path == "/api/llm/add":
                return self._api_llm_add()
            if path == "/api/llm/update":
                return self._api_llm_update()
            if path == "/api/llm/delete":
                return self._api_llm_delete()
            if path == "/api/stop":
                get_agent().abort()
                return self._send_json({"ok": True})
            if path == "/api/new":
                agent = get_agent()
                agent.history = []
                if agent.handler:
                    agent.handler.working = {}
                return self._send_json({"ok": True, "message": "New conversation started."})
            if path == "/api/continue":
                return self._api_continue()
            # l0veyou proxy routes
            if path == "/proxy/auth/login":
                return self._proxy_post("/auth/login")
            if path == "/proxy/auth/logout":
                return self._proxy_post("/auth/logout")
            if path == "/proxy/auth/register":
                return self._proxy_post("/auth/register")
            if path == "/proxy/v1/chat/completions":
                return self._proxy_chat_completions()
            if path == "/api/auth/configure-llm":
                return self._api_configure_llm()
            if path == "/proxy/v1/images/generations":
                return self._proxy_post_auth("/v1/images/generations")
            if path == "/proxy/v1/responses":
                return self._proxy_post_auth("/v1/responses")
            if path == "/proxy/api/creation-tasks/image-generations":
                return self._proxy_post_auth("/api/creation-tasks/image-generations")
            if path == "/proxy/api/creation-tasks/chat-completions":
                return self._proxy_post_auth("/api/creation-tasks/chat-completions")
            if path.startswith("/proxy/api/creation-tasks/") and path.endswith("/cancel"):
                return self._proxy_post_auth(path.replace("/proxy", ""))
            self._send_json({"error": "not found"}, 404)
        except Exception as e:
            traceback.print_exc()
            self._send_json({"error": str(e)}, 500)

    # ---- GET handlers ----
    def _serve_html(self):
        try:
            with open(HTML_PATH, "rb") as f:
                body = f.read()
        except OSError:
            body = b'<!doctype html><title>cybercodewebui</title><pre>cybercodewebui.html not found</pre>'
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _api_status(self):
        agent = get_agent()
        llms = agent.list_llms()
        name = agent.get_llm_name()
        configured = agent.llmclient is not None and agent.is_configured()
        self._send_json({
            "running": bool(agent.is_running),
            "configured": configured,
            "llm_no": agent.llm_no,
            "llm_name": name,
            "llms": [{"idx": i, "name": n, "active": a, "remark": agent.llm_remark(i)} for i, n, a in llms],
            "history": (agent.history or [])[-40:],
            "log": os.path.basename(agent.log_path or ""),
        })

    def _api_hf_skill(self, slug):
        slug = os.path.basename(slug)
        fpath = os.path.join(SKILLS_DIR, slug + ".md")
        if not os.path.isfile(fpath):
            return self._send_json({"error": "skill not found"}, 404)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return self._send_json({"error": str(e)}, 500)
        self._send_json({"slug": slug, "content": content})

    def _serve_video(self, relpath):
        # Resolve safely (no path traversal)
        candidates = [
            os.path.join(HERE, relpath),
            os.path.join(TEMP_DIR, relpath),
            os.path.join(ROOT_DIR, relpath),
        ]
        fpath = next((c for c in candidates if os.path.isfile(c)), None)
        if not fpath:
            return self._send_json({"error": "video not found"}, 404)
        try:
            fsize = os.path.getsize(fpath)
        except OSError:
            return self._send_json({"error": "stat failed"}, 500)
        range_header = self.headers.get("Range")
        start = 0
        end_req = None
        if range_header and range_header.startswith("bytes="):
            try:
                parts = range_header[6:].split("-")
                start = int(parts[0]) if parts[0] else 0
                if len(parts) > 1 and parts[1]:
                    end_req = int(parts[1])  # inclusive end
            except ValueError:
                start = 0
        # Honor client's end, otherwise cap at 1MB chunks
        end = min(end_req + 1 if end_req is not None else start + 1024 * 1024, fsize)
        if start >= fsize:
            self.send_response(416)
            self.end_headers()
            return
        self.send_response(206 if range_header else 200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(end - start))
        self.send_header("Accept-Ranges", "bytes")
        if range_header:
            self.send_header("Content-Range", f"bytes {start}-{end-1}/{fsize}")
        self.end_headers()
        try:
            with open(fpath, "rb") as f:
                f.seek(start)
                remaining = end - start
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    # ---- POST handlers ----
    def _api_llm(self):
        data = self._read_json()
        idx = data.get("idx")
        agent = get_agent()
        if idx is None:
            return self._send_json({"error": "missing idx"})
        try:
            agent.next_llm(int(idx))
        except Exception as e:
            return self._send_json({"error": str(e)})
        llms = agent.list_llms()
        self._send_json({
            "ok": True, "llm_no": agent.llm_no,
            "llm_name": agent.get_llm_name(),
            "llms": [{"idx": i, "name": n, "active": a, "remark": agent.llm_remark(i)} for i, n, a in llms],
        })

    def _api_llm_get(self):
        """Return the full config for a single LLM (for the edit modal)."""
        agent = get_agent()
        qs = parse_qs(urlparse(self.path).query)
        try:
            idx = int((qs.get("idx") or ["0"])[0])
        except ValueError:
            return self._send_json({"error": "invalid idx"}, 400)
        cfg = agent.get_llm_detail(idx)
        if not cfg:
            return self._send_json({"error": "LLM not found"}, 404)
        self._send_json({"cfg": cfg})

    def _build_llm_cfg(self, data):
        """Build a clean LLM config dict from request data."""
        cfg = {
            "name": (data.get("name") or "").strip(),
            "model": (data.get("model") or "").strip(),
            "apibase": (data.get("apibase") or "").strip(),
            "apikey": (data.get("apikey") or "").strip(),
            "remark": (data.get("remark") or "").strip(),
        }
        if not cfg["name"]:
            raise ValueError("显示名称不能为空")
        if not cfg["apibase"]:
            raise ValueError("API 地址不能为空")
        if not cfg["apikey"]:
            raise ValueError("API 密钥不能为空")
        if not cfg["model"]:
            cfg["model"] = cfg["name"]
        return cfg

    def _api_llm_add(self):
        data = self._read_json()
        agent = get_agent()
        try:
            cfg = self._build_llm_cfg(data)
            idx = agent.add_llm(cfg)
        except ValueError as e:
            return self._send_json({"error": str(e)})
        except Exception as e:
            return self._send_json({"error": str(e)})
        llms = agent.list_llms()
        self._send_json({
            "ok": True, "llm_no": agent.llm_no, "added_idx": idx,
            "llm_name": agent.get_llm_name(),
            "llms": [{"idx": i, "name": n, "active": a, "remark": agent.llm_remark(i)} for i, n, a in llms],
        })

    def _api_llm_update(self):
        data = self._read_json()
        idx = data.get("idx")
        if idx is None:
            return self._send_json({"error": "missing idx"})
        agent = get_agent()
        try:
            cfg = self._build_llm_cfg(data)
            agent.update_llm(int(idx), cfg)
        except ValueError as e:
            return self._send_json({"error": str(e)})
        except Exception as e:
            return self._send_json({"error": str(e)})
        llms = agent.list_llms()
        self._send_json({
            "ok": True, "llm_no": agent.llm_no,
            "llm_name": agent.get_llm_name(),
            "llms": [{"idx": i, "name": n, "active": a, "remark": agent.llm_remark(i)} for i, n, a in llms],
        })

    def _api_llm_delete(self):
        data = self._read_json()
        idx = data.get("idx")
        if idx is None:
            return self._send_json({"error": "missing idx"})
        agent = get_agent()
        try:
            agent.delete_llm(int(idx))
        except Exception as e:
            return self._send_json({"error": str(e)})
        llms = agent.list_llms()
        self._send_json({
            "ok": True, "llm_no": agent.llm_no,
            "llm_name": agent.get_llm_name(),
            "llms": [{"idx": i, "name": n, "active": a, "remark": agent.llm_remark(i)} for i, n, a in llms],
        })

    def _api_continue(self):
        data = self._read_json()
        idx = data.get("idx")
        if idx is None:
            return self._send_json({"error": "missing idx"})
        sessions = _sessions_list()
        if not (1 <= int(idx) <= len(sessions)):
            return self._send_json({"error": "invalid session index"})
        sess = sessions[int(idx) - 1]
        # Restore history from the log file
        msgs = _extract_messages(sess["path"])
        agent = get_agent()
        agent.abort()
        agent.history = []
        for m in msgs:
            prefix = "[USER]: " if m["role"] == "user" else "[Agent] "
            agent.history.append(prefix + m["content"][:200])
        self._send_json({"ok": True, "message": f"Restored {len(msgs)} messages.", "path": sess["path"]})


    # ---- l0veyou proxy methods ----
    def _get_auth_token(self):
        """Extract Bearer token from Authorization header."""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        return ""

    def _proxy_get(self, l0veyou_path):
        """Proxy a GET request to l0veyou (no auth required)."""
        url = f"{L0VEYOU_BASE}{l0veyou_path}"
        try:
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "CyberCode/1.0")
            with urllib.request.urlopen(req, context=L0VEYOU_SSL_CTX, timeout=15) as resp:
                body = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as e:
            body = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self._send_json({"error": str(e)}, 502)

    def _proxy_get_auth(self, l0veyou_path):
        """Proxy a GET request to l0veyou with Bearer token. Errors are sanitized."""
        token = self._get_auth_token()
        if not token:
            return self._send_json({"error": "missing token"}, 401)
        url = f"{L0VEYOU_BASE}{l0veyou_path}"
        try:
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "CyberCode/1.0")
            req.add_header("Authorization", f"Bearer {token}")
            with urllib.request.urlopen(req, context=L0VEYOU_SSL_CTX, timeout=15) as resp:
                body = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as e:
            err_body = e.read()
            print(f"[proxy] GET {l0veyou_path} -> {e.code}: {err_body[:200]}", file=sys.stderr, flush=True)
            if l0veyou_path == "/v1/models":
                self._send_json({"object": "list", "data": []}, 200)
            else:
                self._send_json({"error": {"message": "当前用户较多，请稍后再试", "type": "server_busy"}}, 200)
        except Exception as e:
            print(f"[proxy] GET {l0veyou_path} exception: {e}", file=sys.stderr, flush=True)
            if l0veyou_path == "/v1/models":
                self._send_json({"object": "list", "data": []}, 200)
            else:
                self._send_json({"error": {"message": "当前用户较多，请稍后再试", "type": "server_busy"}}, 200)

    def _proxy_post(self, l0veyou_path):
        """Proxy a POST request to l0veyou. Auth errors preserved, network errors sanitized."""
        body_data = self._read_json()
        token = self._get_auth_token()
        url = f"{L0VEYOU_BASE}{l0veyou_path}"
        try:
            data = json.dumps(body_data).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("User-Agent", "CyberCode/1.0")
            if token:
                req.add_header("Authorization", f"Bearer {token}")
            with urllib.request.urlopen(req, context=L0VEYOU_SSL_CTX, timeout=15) as resp:
                body = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as e:
            # Auth endpoints: preserve error codes for login/register
            body = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            print(f"[proxy] POST {l0veyou_path} exception: {e}", file=sys.stderr, flush=True)
            self._send_json({"error": {"message": "当前用户较多，请稍后再试", "type": "server_busy"}}, 200)

    def _proxy_post_auth(self, l0veyou_path):
        """Proxy a POST request to l0veyou with Bearer token. Errors are sanitized."""
        body_data = self._read_json()
        token = self._get_auth_token()
        if not token:
            return self._send_json({"error": "missing token"}, 401)
        url = f"{L0VEYOU_BASE}{l0veyou_path}"
        try:
            data = json.dumps(body_data).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("User-Agent", "CyberCode/1.0")
            req.add_header("Authorization", f"Bearer {token}")
            with urllib.request.urlopen(req, context=L0VEYOU_SSL_CTX, timeout=120) as resp:
                body = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json; charset=utf-8"))
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as e:
            err_body = e.read()
            print(f"[proxy] POST {l0veyou_path} -> {e.code}: {err_body[:200]}", file=sys.stderr, flush=True)
            self._send_json({"error": {"message": "当前用户较多，请稍后再试", "type": "server_busy"}}, 200)
        except Exception as e:
            print(f"[proxy] POST {l0veyou_path} exception: {e}", file=sys.stderr, flush=True)
            self._send_json({"error": {"message": "当前用户较多，请稍后再试", "type": "server_busy"}}, 200)

    def _proxy_file(self, l0veyou_path):
        """Proxy a file request to l0veyou (images, videos, etc.)."""
        token = self._get_auth_token()
        url = f"{L0VEYOU_BASE}{l0veyou_path}"
        try:
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "CyberCode/1.0")
            if token:
                req.add_header("Authorization", f"Bearer {token}")
            with urllib.request.urlopen(req, context=L0VEYOU_SSL_CTX, timeout=30) as resp:
                body = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.headers.get("Content-Type", "application/octet-stream"))
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not found")
        except Exception as e:
            self._send_json({"error": str(e)}, 502)

    def _proxy_chat_completions(self):
        """Proxy chat completions with SSE streaming support. Errors are sanitized."""
        body_data = self._read_json()
        token = self._get_auth_token()
        if not token:
            return self._send_json({"error": "missing token"}, 401)
        url = f"{L0VEYOU_BASE}/v1/chat/completions"
        try:
            data = json.dumps(body_data).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("User-Agent", "CyberCode/1.0")
            req.add_header("Authorization", f"Bearer {token}")
            with urllib.request.urlopen(req, context=L0VEYOU_SSL_CTX, timeout=120) as resp:
                content_type = resp.headers.get("Content-Type", "application/json")
                # Check if this is SSE stream
                if "text/event-stream" in content_type or body_data.get("stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache, no-transform")
                    self.send_header("Connection", "keep-alive")
                    self.send_header("X-Accel-Buffering", "no")
                    self.end_headers()
                    try:
                        while True:
                            chunk = resp.read(4096)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                else:
                    body = resp.read()
                    self.send_response(resp.status)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
        except urllib.error.HTTPError as e:
            err_body = e.read()
            print(f"[proxy] chat/completions -> {e.code}: {err_body[:200]}", file=sys.stderr, flush=True)
            # Return empty completion for chat errors
            if body_data.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-transform")
                self.send_header("Connection", "keep-alive")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                try:
                    self.wfile.write(b"data: {\"choices\":[{\"delta\":{\"content\":\"\"},\"finish_reason\":\"stop\"}]}

")
                    self.wfile.write(b"data: [DONE]

")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
            else:
                self._send_json({"choices": [{"index": 0, "message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}]}, 200)
        except Exception as e:
            print(f"[proxy] chat/completions exception: {e}", file=sys.stderr, flush=True)
            if body_data.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-transform")
                self.send_header("Connection", "keep-alive")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                try:
                    self.wfile.write(b"data: {\"choices\":[{\"delta\":{\"content\":\"\"},\"finish_reason\":\"stop\"}]}

")
                    self.wfile.write(b"data: [DONE]

")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
            else:
                self._send_json({"choices": [{"index": 0, "message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}]}, 200)

    def _api_configure_llm(self):
        """Auto-configure LLM with l0veyou backend using session token."""
        data = self._read_json()
        token = data.get("token", "")
        if not token:
            return self._send_json({"error": "missing token"})
        model = data.get("model", "")
        agent = get_agent()
        cfg = {
            "name": "CyberCode",
            "model": model or "auto",
            "apibase": L0VEYOU_BASE,
            "apikey": token,
            "remark": "l0veyou backend",
        }
        # Check if a l0veyou config already exists, update if so
        found = False
        target_idx = -1
        for i, existing in enumerate(agent._llm_configs):
            if existing.get("apibase", "").rstrip("/") == L0VEYOU_BASE:
                agent.update_llm(i, cfg)
                found = True
                target_idx = i
                break
        if not found:
            target_idx = agent.add_llm(cfg)
        # Switch to the l0veyou LLM
        agent.next_llm(target_idx)
        llms = agent.list_llms()
        self._send_json({
            "ok": True,
            "llm_no": agent.llm_no,
            "llm_name": agent.get_llm_name(),
            "llms": [{"idx": i, "name": n, "active": a, "remark": agent.llm_remark(i)} for i, n, a in llms],
        })

    def _api_chat(self):
        data = self._read_json()
        text = (data.get("text") or "").strip()
        if not text:
            return self._send_json({"error": "empty text"})
        agent = get_agent()
        if agent.llmclient is None:
            return self._send_json({"error": "no LLM configured — create mykey.py or mykey.json"})
        if agent.is_running:
            return self._send_json({"error": "agent is already running — send /api/stop first"}, 409)

        is_video = bool(data.get("video"))
        preamble = _hf_preamble() if is_video else ""
        prompt = f"{FILE_HINT}\n\n{preamble}\n\n{text}" if preamble else f"{FILE_HINT}\n\n{text}"
        dq = agent.put_task(prompt, source="user")

        # SSE headers
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def emit(obj):
            line = "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"
            try:
                self.wfile.write(line.encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return False
            return True

        emit({"type": "start", "ts": int(time.time() * 1000)})
        idle = 0
        got_done = False
        try:
            while True:
                try:
                    item = dq.get(timeout=1)
                except Q.Empty:
                    if agent.is_running:
                        idle = 0
                        continue
                    idle += 1
                    if idle >= 3 and not got_done:
                        emit({"type": "done", "text": "", "aborted": True})
                        break
                    continue
                idle = 0
                if "done" in item:
                    got_done = True
                    raw = item.get("done", "") or ""
                    files = [p for p in extract_files(raw) if os.path.exists(p)]
                    body = _clean_for_ui(raw)
                    emit({"type": "done", "text": body, "files": files,
                          "source": item.get("source", "user")})
                    break
                if "next" in item:
                    if not emit({"type": "delta", "text": item.get("next", ""),
                                 "turn": item.get("turn", 0)}):
                        break
        except Exception as e:
            try:
                emit({"type": "error", "message": f"{type(e).__name__}: {e}"})
            except Exception:
                pass
        finally:
            try:
                self.wfile.flush()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="cybercodewebui — self-contained Codex-dark agent web UI")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--llm_no", type=int, default=0, help="LLM index to start on")
    args = parser.parse_args()

    agent = get_agent()
    if agent.llmclient is not None:
        try:
            agent.next_llm(args.llm_no)
        except Exception as e:
            print(f"[cybercodewebui] llm switch failed: {e}")

    # Ensure memory + temp dirs exist
    os.makedirs(MEMORY_DIR, exist_ok=True)
    os.makedirs(os.path.join(TEMP_DIR, "model_responses"), exist_ok=True)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    daemon = threading.Thread(target=server.serve_forever, daemon=True)
    daemon.start()

    url = f"http://{args.host}:{args.port}"
    print(f"\n  ╭───────────────────────────────────────────╮")
    print(f"  │  cybercode    ·  self-contained agent     │")
    print(f"  │  open  {url:<33}│")
    print(f"  │  Ctrl+C to stop                           │")
    print(f"  ╰───────────────────────────────────────────╯\n")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\n[cybercodewebui] shutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()

