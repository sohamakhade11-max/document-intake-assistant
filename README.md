# Document Intake Assistant

> **Fictional — Not Legal Advice.** This is a technical-assessment demo that interviews a user and drafts a
> fictional *Personal Wishes Document*. It is not a legal product and must not be used for real documents.

## Overview

A small full-stack app: a chat interview on the left, the **structured state** on the right, and a live
**document preview** below. The backend owns a typed state object (the source of truth). An LLM (or a
deterministic mock) only *proposes* updates; the backend validates every proposal, applies the valid ones, decides
deterministically what to ask next, and generates the document **from state only**.

It runs with **no API key** (default `LLM_PROVIDER=mock`).

## Architecture

```
Browser
   |
   v
React + TypeScript (Vite)      chat | structured state | document preview
   |   /api (proxied)
   v
FastAPI  (api.py: routes, error envelope -- no business logic)
   |
   v
ConversationService (service.py: orchestrates one turn)
   |
   +-- LLMProvider (llm/)  -- Mock | OpenAI-compatible  -> raw JSON text
   +-- parsing.py          -- raw text -> LLMResponse (Pydantic)   [reject malformed]
   +-- state_updates.py    -- per-update validation, evidence check,
   |                          conflict detection, apply to a COPY   [reject invalid]
   +-- flow.py             -- completeness, field statuses, next question (deterministic)
   +-- store.py            -- ConversationStore (in-memory implementation)
   +-- document.py         -- pure function: state -> document
```

One turn: `user message -> LLM proposes JSON -> parse -> validate each update -> apply valid ones ->
detect conflicts -> backend picks next question -> save -> return state + document`.

## Tech stack

Python 3.11+ / FastAPI / Pydantic v2 / httpx / pytest(+asyncio) · React 18 / TypeScript / Vite (plain CSS).

## Project structure

```
backend/
  app/
    main.py            app wiring (create_app with injectable provider/store)
    api.py             routes + consistent error handlers
    schemas.py         API request/response models
    models.py          PersonalWishesState and related domain models
    service.py         conversation orchestration
    state_updates.py   validation + application of LLM proposals
    flow.py            deterministic completion logic / next question
    document.py        document generation
    store.py           ConversationStore protocol + in-memory store
    config.py          env-based settings (read lazily; never crashes on missing key)
    llm/               base (contract+errors), parsing, prompt, mock, openai_provider, factory
  tests/               behavioural tests, fixtures/llm_responses.json
frontend/src/          App, api client, ChatPanel, StatePanel, DocumentPanel
AI_LOG.md   .env.example   .gitignore
```

## Setup

Requires Python 3.11+ and Node 18+.

```bash
git clone <your-repo-url> document-intake-assistant
cd document-intake-assistant

# backend
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd ..
cp .env.example .env                 # optional; defaults work (mock provider)

# frontend
cd frontend
npm install
```

### Environment variables (`.env.example`)

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock` or `openai` (`openai` means "any OpenAI-compatible API", including Google Gemini; there is no separate `gemini` value) |
| `OPENAI_API_KEY` | empty | Required only for `openai`. Never commit it. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Any chat model that supports JSON mode (e.g. `gemini-3.5-flash` for Gemini) |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint |
| `LLM_TIMEOUT_SECONDS` | `30` | Upstream timeout |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated |

`.env` is found by searching upward from the backend code, so a repo-root `.env` (from `cp .env.example .env`) works; real environment variables take precedence.
`.env` is git-ignored; only `.env.example` is committed.

## Running

```bash
# terminal 1
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# terminal 2
cd frontend && npm run dev          # http://localhost:5173 (proxies /api to :8000)
```

If the key is missing the app still starts; the UI shows a banner and message requests return a clear `503`.

### Using a real LLM

Any OpenAI-compatible chat API works by changing four variables in `.env` (then **restart the backend**, since `.env` is read at startup).

**Google Gemini (tested with `gemini-3.5-flash`)** — free tier available:

1. Create a key at <https://aistudio.google.com/apikey>.
2. Put this in `.env` (no quotes, no spaces around `=`):
   ```
   LLM_PROVIDER=openai
   OPENAI_API_KEY=your-gemini-key
   OPENAI_MODEL=gemini-3.5-flash
   OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
   ```
3. Restart the backend and check `http://127.0.0.1:8000/api/health` shows `"llm_provider":"openai","llm_configured":true`.

Notes from testing:
- **Model names change and differ per key.** A name listed by the models endpoint can still return 404 for chat
  (`gemini-2.5-flash` did on my key). List what your key can use with
  `GET https://generativelanguage.googleapis.com/v1beta/openai/models` (header `Authorization: Bearer <key>`),
  then try a name in a quick chat call before putting it in `.env`. `gemini-flash-latest` also worked, but I use an
  explicit version for reproducibility.
- **Transient errors happen on free tiers** (HTTP 503 "overloaded", 429 rate limit). The provider retries these up to
  3 times with a short backoff before returning a friendly "busy" error (see Failure handling).
- **Privacy:** free tiers may log or train on requests. Use made-up data only (e.g. "Jane Smith") when testing.
- The base URL must end at `/openai`; the app appends `/chat/completions` itself.

Other OpenAI-compatible providers (OpenAI, Groq, OpenRouter, a local Ollama server) use the same four variables with
their own key, model name and base URL. Only Gemini has been tried; the others are untested here.

### Try it (mock provider)

Mock mode is a small rule-based English extractor that speaks the same JSON contract as a real model.
Suggested script: `Jane Smith` → `I live at 12 Oak Road, Pune` → `yes` → `I don't have children` →
`I want everything divided between my two children` (contradiction question) →
`I actually do have children — Sarah and Daniel` (correction) → `My brother James` → `Change my executor to Sarah`.

Failure-injection tags (start a message with one): `[mock:malformed]`, `[mock:invalid-type]`, `[mock:missing-keys]`,
`[mock:timeout]`, `[mock:error]`.

## Running tests

```bash
cd backend && source .venv/bin/activate && pytest
cd ../frontend && npm run build      # typecheck + production build
```

## API contract

All endpoints are under `/api`. Errors always look like `{"error": {"code": "...", "message": "..."}}` — no stack traces.

| Method & path | Purpose | Success |
|---|---|---|
| `GET /health` | provider name + whether it is configured | `{status, llm_provider, llm_configured}` |
| `POST /conversations` | start an interview (first question included) | `201 ConversationView` |
| `GET /conversations/{id}` | full view (messages, state, statuses, document) | `ConversationView` |
| `GET /conversations/{id}/state` | state + `field_statuses` + `missing_required` + `pending_conflicts` + `is_complete` | `StateView` |
| `GET /conversations/{id}/document` | draft document `{title, disclaimer, status, sections[], text}` | `DocumentView` |
| `POST /conversations/{id}/messages` body `{"message": "..."}` (1–2000 chars) | one turn | `{assistant_message, warnings[], conversation}` |

| Status | `error.code` | When |
|---|---|---|
| 404 | `conversation_not_found` | unknown id |
| 422 | `invalid_request` / `invalid_message` | empty / too long / malformed body |
| 502 | `llm_unavailable` | model API error / unreachable |
| 503 | `llm_not_configured` | provider selected but no key |
| 504 | `llm_timeout` | model timed out |
| 500 | `internal_error` | anything unexpected (details only in server logs) |

A **malformed or invalid model response is not an HTTP error**: the turn returns `200` with a fallback assistant
message and `warnings`, state unchanged. A *transport* failure (timeout/outage) returns an error and the turn is
not recorded, so the user can simply resend.

### Structured state (`PersonalWishesState`)

```json
{
  "full_name": "Jane Smith", "home_address": "12 Oak Road", "covers_worldwide_assets": true,
  "has_children": true, "children": ["Sarah", "Daniel"],
  "executor": {"name": "James", "relationship": "brother"},
  "specific_gifts": [{"description": "my watch", "recipient": "Tom"}],
  "additional_wishes": []
}
```
`null` = unknown. `false` = explicit "no". `[]` for gifts/wishes = user explicitly said none (`null` = not yet asked).
`field_statuses` reports each field as `unknown | confirmed | incomplete | needs_clarification`
("confirmed" = supplied by the user, passed validation, and not under a pending conflict).

### LLM contract (what a provider must return, as JSON text)

```json
{
  "acknowledgement": "short neutral sentence",
  "updates": [{"field": "executor.name", "value": "James", "operation": "set",
               "is_correction": false, "evidence": "exact words from the user's message"}],
  "needs_clarification": [{"field": "specific_gifts", "question": "..."}],
  "keep_existing_fields": []
}
```
I deliberately dropped a model-supplied `ready_to_generate` flag: completeness is computed by the backend.

## Design decisions

- **Structured state is the source of truth.** The model sees the current state each turn (plus a 6-message
  window as context only) and the document is generated from state, never from the transcript.
- **LLM output is untrusted.** Parse → validate whole-response shape → validate each update independently
  (known field, type, length, strict booleans, valid operation). One bad update never blocks the good ones, and
  nothing is merged unvalidated. Updates are applied to a copy and the result re-validated as a whole.
- **Evidence rule against invented facts.** Every update must include a quote that actually appears in the user's
  message; otherwise it is discarded. So "My executor is James" cannot become `relationship: "brother"` even if a
  model tries. (Trade-off: a model that paraphrases its evidence gets updates dropped; the prompt says "verbatim".)
- **Backend decides what to ask.** The reply is the model's short acknowledgement + a deterministic next question
  from `flow.py`, so captured fields are never re-asked and "done" is never the model's call. A pending
  contradiction outranks a model clarification, which outranks the next missing field.
- **Contradictions vs corrections.** A proposed value that differs from a known value is *applied* only if the
  model marks `is_correction` ("actually…", "change…") or the user is answering a pending question. Otherwise it
  becomes a pending `Conflict`, state is untouched, and the assistant asks "Earlier I recorded X, but … suggests Y.
  Which is correct?". Replying with a correction applies it; replying "keep it" (or restating the old value)
  clears it. Changing the executor's name clears the old relationship (it described the previous person).
  Setting `has_children=false` clears children; adding children when `has_children=false` is a conflict.
- **"Everything to my wife" is not a gift.** The schema only models specific gifts (item + recipient); broad
  estate instructions trigger a clarification instead of being force-fit.
- **Provider abstraction.** `LLMProvider.process_message(LLMRequest) -> raw text`. Mock, OpenAI-compatible and test
  doubles all go through identical parsing/validation. Swapping providers = implement one method + register it in
  `llm/factory.py`.
- **Mock mode** exists so the app is fully demoable and testable offline. Real behaviour (with the model) is
  broader than the mock's regex rules.
- **In-memory store** behind `ConversationStore` for simplicity. State is lost on restart (the UI starts a new
  conversation if its saved id is gone). Replacing it means implementing `create/get/save`.
- **Document generation** is a pure function of state; unknown required values render as `[Not yet provided]`,
  the preview is labelled *incomplete draft* until required fields are complete, and the disclaimer
  "Fictional — Not Legal Advice" appears at top and bottom. The frontend renders text nodes only (no `innerHTML`).

## Failure handling

| Situation | Behaviour |
|---|---|
| Malformed JSON / wrong shape / missing keys | `200`, state unchanged, apology + re-ask, `warnings` shown |
| Invalid type for a field (e.g. `full_name: 123456`) | that update is rejected, previous value kept |
| Unknown field / unsupported evidence | update rejected and reported |
| Transient upstream error (429 / 5xx) | Retried up to 3 times with backoff; if it still fails: `502` "busy, try again", turn not recorded, input preserved in UI |
| Timeout / other upstream error (e.g. 401, 404) | `504` / `502` immediately (not retried), turn not recorded, input preserved in UI |
| Missing API key | app starts; `/health` reports not configured; messages → `503`; UI banner |
| Unexpected exception | generic `500`; stack trace logged server-side only |

Logs contain conversation ids, field names and error categories, **not** user message content or API bodies.

## Production improvements (not implemented)

Persistent store (PostgreSQL) and Redis for sessions/locks; authentication and per-user ownership of conversations;
encryption at rest and retention/deletion policy for personal data; rate limiting and request-size/cost budgets;
structured logging, tracing and metrics (token usage, rejection rates); provider/model fallback, jittered retries and circuit breaking (only simple bounded retries exist today);
JSON-schema/tool-calling structured outputs from the provider instead of JSON mode; an append-only audit trail of
state changes; prompt versioning and an offline eval set (the `PROMPT_VERSION` constant is only a stub);
stronger semantic validation (address/name checks, duplicate detection); a per-conversation lock that works across
processes (the current one is per-process); accessibility review and frontend tests; real legal review before
anything resembling a real document.

## Known limitations

Real-model behaviour has been checked by hand against Gemini (`gemini-3.5-flash`) only, with no automated tests against a live API; provider HTTP behaviour (retries, errors) is covered by tests using a mock transport. The mock extractor is English-only and rule-based. The in-memory store and locks are single-process. Prompt-injection
defences are limited to treating user text as data, strict schema validation and the evidence rule; no moderation is
performed. Gifts record a free-text description and recipient only. The executor's address is intentionally not stored.
