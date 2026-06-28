# cybercodewebui — Codex-dark Web UI with a Built-in Self-Evolving Agent

A standalone, self-contained web UI + agent framework styled after the
Codex-dark interface. **No external agent dependency** — the entire agent
core (LLM client, agent loop, 9 atomic tools, layered memory) ships inside
`agent_core.py` and runs from a single directory.

![cybercode](https://img.shields.io/badge/npm-cybercode-6b8cff) ![deps](https://img.shields.io/badge/dependencies-stdlib+requests-28c840) ![py](https://img.shields.io/badge/python-3.11%2B-blue) ![license](https://img.shields.io/badge/license-MIT-blue)

## Quick Start

```bash
npx cybercode
```

That's it. On first run it:
1. Finds Python 3.11+ on your system
2. Installs `requests` if missing
3. Copies the bundled agent + skills to `~/.cybercode/`
4. Creates a `mykey.json` template (edit it with your API key)
5. Starts the web UI and opens your browser

## Attribution & License

The agent core architecture in `agent_core.py` was developed with reference to
[**GenericAgent**](https://github.com/lsdefine/GenericAgent) by lsdefine
(MIT License, Copyright © 2025 lsdefine). We gratefully acknowledge the
GenericAgent project — its ~100-line agent loop, 9-atomic-tool design, and
layered memory concept directly inspired this implementation.

The bundled HyperFrames skills (`skills/`) originate from
[**HyperFrames**](https://github.com/heygen-com/hyperframes) by HeyGen
(MIT License).

See `LICENSE` for the full MIT license text, including the GenericAgent
copyright notice as required by its license terms.

## What it is

`cybercodewebui.py` boots a self-contained `Agent` (from `agent_core.py`), serves
`cybercodewebui.html` at `/`, and exposes a JSON + SSE API the page talks to.
The UI keeps the Codex-dark look — blue radial-gradient desktop, traffic-light
window chrome, dark sidebar with threads + skills, centered *Let's build*
empty state, pill LLM switcher, rounded composer with Local/Worktree/Cloud
modes — but every control is wired to the built-in agent.

**Standalone: no GenericAgent dependency.** The agent core (`agent_core.py`)
is a from-scratch reimplementation that ships in this repo. You do **not** need
GenericAgent installed. The only runtime dependency is `requests` (for the LLM
HTTP client); everything else uses the Python stdlib.

## Files

```
cybercodewebui/
├── package.json       # npm package config (bin, files, metadata)
├── bin/
│   └── cli.mjs        # Node.js launcher (finds Python, bootstraps, opens browser)
├── python/
│   ├── agent_core.py       # Self-contained agent core (LLM client + loop + 9 tools + memory)
│   ├── cybercodewebui.py      # stdlib HTTP server + SSE + API
│   └── cybercodewebui.html    # Codex-dark UI (single file, no build step)
├── skills/             # HyperFrames video skills (12 files, from HeyGen)
├── templates/
│   └── mykey_template.json  # API key template (auto-copied on first run)
├── LICENSE             # MIT (includes GenericAgent + HyperFrames copyright notices)
└── README.md           # This file
```

## Manual (without npx)

If you prefer to run the Python server directly:

```bash
# 1. Configure your LLM (any OpenAI-compatible endpoint)
cat > mykey.json << 'EOF'
{
  "llm1": {
    "apikey": "sk-your-key-here",
    "apibase": "https://api.openai.com",
    "model": "gpt-4o",
    "name": "GPT-4o"
  }
}
EOF

# 2. Install requests (only dependency)
pip install requests

# 3. Run
python python/cybercodewebui.py                 # http://127.0.0.1:18600
```

## Supported LLM providers

Any OpenAI-compatible chat completions endpoint works:
- **OpenAI** (GPT-4o, o1, o3, etc.)
- **DeepSeek**
- **Kimi / Moonshot**
- **MiniMax**
- **Local models** via Ollama, LM Studio, vLLM, etc.
- **Anthropic Claude** via OpenAI-compatible proxies

## What works

| UI element | Wired to |
| :--- | :--- |
| **Composer + send** | `agent.put_task()` → SSE stream of deltas + final `done` |
| **Stop button / red send toggle** | `agent.abort()` |
| **New thread** | `/api/new` → clears conversation history |
| **Thread list (sidebar)** | `/api/sessions` → scans `temp/model_responses/` logs |
| **Click a thread** | `/api/continue` → restores that session + replays bubbles |
| **LLM pill + dropdown** | `/api/llm` → `agent.next_llm(idx)` |
| **Skills panel (sidebar)** | `/api/skills` → lists `memory/` SOPs and skill files |
| **Suggest tasks** | prefills the autonomous-planning prompt |
| **Status dot** | `agent.is_running` polled every 4s |
| **Tool / file refs** | `🛠️ Tool: \`name\`` lines → tool chips; `[FILE:path]` → clickable file chips |
| **Turn folding** | `**LLM Running (Turn N) ...**` markers → collapsible turn sections |
| **Make video button** | Injects HyperFrames skill preamble + `/video` command |
| **Video gallery** | `/api/videos` → scans for rendered `.mp4` files |
| **Video playback** | `/api/video/<path>` → streams with Range support (seekable) |

## The 9 Atomic Tools

The agent core exposes exactly 9 tools (same design philosophy as GenericAgent):

| Tool | Function |
| :--- | :--- |
| `code_run` | Execute Python or shell scripts |
| `file_read` | Read files with line numbers, keyword search |
| `file_write` | Create / overwrite / append files |
| `file_patch` | Patch a unique text block in a file |
| `web_scan` | Fetch and simplify web pages (urllib-based) |
| `web_execute_js` | Execute JS in a browser (requires TMWebDriver; degrades gracefully) |
| `ask_user` | Interrupt to ask the user a question |
| `update_working_checkpoint` | Short-term working memory notepad |
| `start_long_term_update` | Distill experience into long-term memory |

## HyperFrames — Built-in Video Generation

The HyperFrames skill pack (12 files) is bundled in `skills/`. Click the
**Make video** button in the sidebar, or type `/video <description>`. The agent
reads the bundled skills and uses the `npx hyperframes` CLI to render HTML
compositions into `.mp4` files. Rendered videos appear in the sidebar gallery
and can be played inline.

## API Reference

| Method | Path | Description |
| :--- | :--- | :--- |
| GET | `/` | The web UI |
| GET | `/api/status` | Agent status: running, LLM, history |
| GET | `/api/sessions` | Recoverable sessions (log files) |
| GET | `/api/skills` | Agent memory/SOP files |
| GET | `/api/messages?path=...` | Replay messages from a session log |
| GET | `/api/hyperframes` | List bundled HyperFrames skills |
| GET | `/api/hyperframes/<name>` | Raw skill markdown |
| GET | `/api/videos` | Rendered `.mp4` files |
| GET | `/api/video/<path>` | Stream a video (Range-supported) |
| POST | `/api/chat` | SSE stream: delta / done / error |
| POST | `/api/llm` | Switch LLM by index |
| POST | `/api/stop` | Abort current task |
| POST | `/api/new` | Start fresh conversation |
| POST | `/api/continue` | Restore session N |
| POST | `/api/btw` | Side question (while task runs) |

## License

MIT License — see `LICENSE` for full text.

This project's agent core was developed with reference to
[GenericAgent](https://github.com/lsdefine/GenericAgent) (MIT, Copyright © 2025
lsdefine). The GenericAgent copyright notice is included in `LICENSE` as
required by its license terms. HyperFrames skills are MIT-licensed by HeyGen.
