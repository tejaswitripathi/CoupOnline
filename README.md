# Coup

A desktop app for playing the bluffing card game **Coup** against LLM opponents.
You sit at a table with agents backed by GPT, Claude, and Gemini (or a local
heuristic bot), and every AI turn is driven by a real model call — including the
public "table talk" and private reasoning shown on screen. You can also spectate
a table of pure AI players.

## How it's built

The project is a monorepo with a thin desktop shell around a web UI and a Python
game server:

- **Frontend** (`frontend/`) — React 19 + TypeScript, built with Vite, animated
  with Framer Motion, routed with React Router. It is a pure renderer/driver: it
  fetches authoritative game state from the backend, asks agents to act, and
  paints the table, thoughts, and game log.
- **Desktop shell** (`electron/`) — Electron loads the Vite dev server in
  development and the static `dist/` build when packaged.
- **Backend** (`backend/`) — a FastAPI service that owns all game logic:
  - `coup-core/` — the rules engine (state, actions, resolver, card/player
    models).
  - `coup-api/` — FastAPI app, routes, request/response schemas, and the
    in-memory game store.
  - `agents/` — LLM agent implementations (`gpt_agent`, `claude_agent`,
    `gemini_agent`) plus a base class and a no-key heuristic agent.
  - `orchestration/` — `match_runner` for stepping games forward.
  - `database/` — optional MongoDB integration used for research/logging.

The **backend is authoritative**: the frontend never simulates the game locally.
Each AI turn is an HTTP call that returns the agent's decision and its
public/private thoughts, which the UI renders in the thought bubble and game log.

```
frontend/   React + Vite renderer (the game UI)
electron/   Electron main process (desktop window)
backend/    FastAPI game server, rules engine, and LLM agents
docs/        design notes
scripts/     asset helpers
```

## Prerequisites

- **Node.js 18+** (for the frontend, Vite, and Electron)
- **Python 3.10+** (for the FastAPI backend)
- API keys for whichever LLM providers you want to play against. The heuristic
  ("Random") agent needs no key, so you can run the whole thing key-free.

## Setup

1. **Install Node dependencies** (from the repo root):

   ```bash
   npm install
   ```

2. **Create the Python virtual environment and install backend deps.** The dev
   script expects the venv at the repo root in `.venv`:

   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r backend/requirements.txt
   ```

3. **Add API keys** (optional — only needed for the LLM agents). Create a `.env`
   file at the repo root:

   ```bash
   OPENAI_API_KEY=sk-...
   ANTHROPIC_API_KEY=sk-ant-...   # or CLAUDE_API_KEY
   GEMINI_API_KEY=...
   ```

   The backend discovers `.env` by walking up from the working directory, so the
   repo root is a good place for it. `.env` is gitignored.

## Running the app

Start everything (FastAPI backend, Vite dev server, and Electron) with one
command from the repo root:

```bash
npm run dev
```

This runs three processes concurrently:

- `dev:api` — FastAPI on `http://127.0.0.1:8000` (auto-reload)
- `dev:web` — Vite on `http://127.0.0.1:5173`
- `dev:electron` — waits for both ports, then opens the desktop window

Once the window opens, add agents in the lobby, choose whether to play or
spectate, and start the game.

### Individual processes

You can also run pieces on their own:

```bash
npm run dev:api        # backend only
npm run dev:web        # frontend only (browser at http://127.0.0.1:5173)
npm run electron       # Electron against an already-running dev server
```

### Production build

```bash
npm run build          # type-check + Vite build into dist/
npm run preview        # serve the built frontend
```

When packaged, Electron loads the static build from `dist/`; the FastAPI backend
still needs to be running for games to work.

## Configuration

- **API location** — the frontend talks to `http://127.0.0.1:8000/api/v1` by
  default. Override with the `VITE_API_ROOT` environment variable at build/dev
  time.
- **CORS** — the backend allows the Vite dev origin and the packaged Electron
  (`file://`) origin out of the box.
