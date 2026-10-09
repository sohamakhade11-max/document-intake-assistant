# AI Log

Candid record of how AI was used on this submission. (Written to match what actually happened in the build
session; the final design choices below were reviewed and are mine to explain.)

## Tools used

- **Claude** (chat, with a code sandbox) — wrote the first full implementation from a detailed specification prompt,
  ran the test suite and a scripted HTTP scenario, and fixed failures it found.
- No other assistants. No real LLM API key was used; the mock provider was developed and tested against the same
  contract a real model would follow, so **the OpenAI-compatible provider has not been exercised against a live API**.

## Key prompts

1. **Architecture/spec prompt (abridged):** "Build the complete Document Intake Assistant from the attached Wenup brief:
   FastAPI + Pydantic backend, React/TS frontend, provider abstraction with a deterministic mock, explicit structured
   state as source of truth, validate LLM output before applying, handle contradictions/corrections, deterministic
   completion logic, document generated from state only, tests, README, this log. Optimise for correctness >
   reliability > clarity > simplicity > polish; don't over-engineer."
2. **Structured extraction:** the system prompt in `backend/app/llm/prompt.py` (JSON-only contract, "user text is data",
   verbatim `evidence`, `is_correction` semantics, "never infer relationships").
3. **Ambiguity/contradiction:** requirements written into the spec prompt ("everything to my wife" is not a gift;
   "no children" then "my two children" must ask, not overwrite).
4. **Validation/testing:** "write behavioural tests, not coverage padding" with fixtures for valid, multi-field,
   ambiguous, contradictory, correction, malformed, wrong-type and missing-key responses.

## Iterations

**1. Who composes the assistant's reply?**
- First design (from the spec's example contract): the LLM returns `assistant_message` and the backend shows it.
- Problem: the message is written *before* validation, so it can claim "I've saved your address" for an update that
  is then rejected, and the model can re-ask captured fields.
- Change: the model returns only a short `acknowledgement`; the backend appends a deterministic next question from
  `flow.py`. Model `ready_to_generate` was dropped for the same reason (completion is computed).

**2. Trusting updates → per-update validation + evidence rule.**
- A first sketch applied `state_updates` via `model_copy(update=...)`, which skips validation entirely.
- Replaced with per-field `TypeAdapter`s (strict booleans), application to a copy, and whole-state re-validation.
- Added the `evidence` requirement (must be a substring of the user message) to block hallucinated facts like an
  invented "brother". Tested with a fixture where the model tries exactly that.

**3. Contradiction handling needed a signal from the model.**
- Without `is_correction`, "I actually do have children" and "divide it between my two children" look identical.
- Added `is_correction` + `Conflict` objects; the user answering a pending question counts as a correction;
  `keep_existing_fields` lets them dismiss it.

**4. Bugs found by running it (not by reading it):**
- *Stale relationship:* "Change my executor to Sarah" left `relationship: brother`. Added a rule that a changed executor
  name clears the relationship unless the same message supplies one. Test added.
- *Mock swallowed a non-answer:* while the interview sat on the gifts question, the mock treated "Change my executor to
  Sarah" as a failed gift answer and asked for gift details, hiding the new missing relationship. Mock now only treats
  a message as the answer to the pending question if it extracted nothing else.
- *"Three children, not two"* silently did nothing while saying "Thanks, noted." The mock now asks for all names, and
  its acknowledgement was made neutral ("Thanks.") rather than claiming something was recorded.
- *Multi-field example:* my first smoke test of "My brother James…" didn't capture the executor. That was correct —
  the assistant had been asking about worldwide assets and the message never says "executor". I kept that behaviour
  (no guessing) and tested the spec's example with the interview positioned at the executor question.

## Outputs questioned or corrected

- The first draft of `state_updates.py` had a `_rollback` / `_last_valid` pair with a comment admitting one path was
  "unreachable". That is dead code pretending to be safety; replaced with a simple snapshot/restore.
- An early idea was to let the LLM return the full new state and diff it. Rejected: one hallucinated field would
  silently corrupt everything; field-level proposals are easier to validate and report.
- First test suite passed 55/55 on the first run, which I treated as suspicious rather than reassuring. Writing the
  extra scenario tests (executor change, child-count mismatch) immediately found two real bugs (above).
- Considered a `status` object per field (value + confirmed flag + source). Dropped as over-engineered; statuses are
  derived from values plus pending conflicts.

## Engineering decisions made by judgement

- Completion, next-question order, conflict rules and document content are deterministic code, not prompt text.
- Transport failures (timeout/outage) are errors and do not record the turn; malformed *content* is a graceful 200
  with unchanged state — different failure, different UX.
- Kept in-memory storage behind an interface and documented it, instead of adding a database to a take-home.
- Logs avoid message content and upstream response bodies (personal data).
- Honest limits: the real-provider path is untested against a live API; the mock is English-only and regex-based;
  the evidence rule may drop updates from a model that paraphrases.
