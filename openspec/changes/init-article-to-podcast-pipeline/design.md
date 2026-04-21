## Context

Lazy Podcast Mate is a greenfield local-first Python tool that turns a single article (Markdown, TXT, or HTML) into a publish-ready MP3 podcast episode. The target user is an individual technical creator running the tool on a stock laptop (Windows/macOS/Linux), without GPUs or container infrastructure. The pipeline depends on two external commercial services: an LLM for script rewriting and a TTS service for voice synthesis. The toolchain also depends on `ffmpeg` via `pydub` for audio post-production. There is no existing codebase to migrate; this change establishes the entire module layout, configuration surface, and runtime contract.

Key constraints:

- Must be runnable by a single `python -m lazy_podcast_mate ...` (or equivalent CLI) command against a file path, with no manual steps between stages.
- Must tolerate flaky network / rate-limited LLM and TTS calls and be resumable after any stage fails.
- Must keep secrets out of source and logs, and must keep core text content local (only the text that must be sent to LLM/TTS leaves the machine).
- Must be modular so that swapping LLM or TTS providers does not require changes in orchestration, post-production, or output modules.
- Must produce stylistically consistent episodes: "calm, seasoned, informed narrator" voice and a fixed structural template (intro → body with transitions → closing).

## Goals / Non-Goals

**Goals:**

- Deliver a four-layer, modular Python package that implements the full article-to-MP3 pipeline end-to-end.
- Establish a stable provider-abstraction layer so LLM and TTS vendors are interchangeable via config only.
- Establish a checkpoint + run-log mechanism so a single failing stage can be retried without redoing earlier stages.
- Ship a `.env.example`, a `config.yaml` with sensible defaults, a `README`, and one runnable example so a new user can produce their first episode in under 30 minutes.
- Produce 320 kbps MP3 output with correct ID3 tags and loudness suitable for podcast distribution.

**Non-Goals:**

- Feishu (Lark) document webhook ingestion — deferred to Sprint 3.
- RSS feed generation and multi-platform auto-distribution — deferred to Sprint 3.
- Any graphical UI, web console, or hosted service — CLI only for this change.
- Voice cloning or training of custom TTS models — only parameter-level voice selection against managed TTS providers.
- Multi-speaker / dialogue-style podcasts — single narrator only in this change.
- Real-time / streaming synthesis — batch-only pipeline.

## Decisions

### Decision 1: Language and runtime

**Choice:** Python 3.10+, standard `venv` + `requirements.txt`.

**Rationale:** Requested in the brief; mature ecosystem for both LLM SDKs and audio tooling (`pydub`, `ffmpeg`). Python 3.10 gives us structural pattern matching and modern typing features without pinning too new a minor version.

**Alternatives considered:** Node.js (weaker audio ecosystem), Go (poor LLM SDK coverage for domestic providers), Poetry/uv (adds setup friction; `requirements.txt` is enough for MVP and upgradable later).

### Decision 2: Four-layer package layout

**Choice:** A single package `lazy_podcast_mate` with modules grouped by layer:

```
lazy_podcast_mate/
  ingestion/    # readers for md/txt/html, Article dataclass
  cleaning/     # rule-based cleaner + term dictionary
  script/       # LLM provider interface + prompt builder
  chunking/     # semantic chunker for TTS-sized segments
  tts/          # TTS provider interface + concrete adapters
  post/         # pydub-based concat, fades, BGM mix, normalise
  output/       # ID3 tagging, filename rules, history log
  orchestrator/ # stage runner, checkpoint store, run log
  config/       # .env + yaml loader, validation
  cli.py
```

**Rationale:** Matches the four architectural layers described in the brief (input ingestion, core processing, audio generation, output management) and gives each stage a single-responsibility home. It also makes per-stage unit testing straightforward.

**Alternatives considered:** Flat module layout (breaks down as the number of providers grows), plugin-based dynamic loader (overkill for Sprint 1 — can be introduced later without breaking the interface).

### Decision 3: Provider abstraction via small Protocols

**Choice:** Define two narrow interfaces:

- `ScriptRewriter.rewrite(cleaned_text: str, *, metadata: ArticleMetadata) -> str`
- `TTSSynthesizer.synthesize(chunk: TextChunk, *, voice: VoiceConfig) -> bytes` (returns mp3/wav bytes) plus a `supports_concurrency: int` attribute.

Concrete adapters live next to the interface (e.g. `script/openai_compatible.py`, `tts/volcano.py`, `tts/azure.py`, `tts/cosyvoice.py`). A `registry` dict maps a `provider` string from config to a factory.

**Rationale:** Tiny surface area, no heavy base classes; matches the brief's "standardised third-party interface" requirement while keeping the core code vendor-agnostic. A new provider = one file plus a registry entry.

**Alternatives considered:** Full plug-in discovery via entry points (heavy for MVP), dependency injection framework (adds indirection with no benefit at this scale).

### Decision 4: Prompt contract for script rewriting

**Choice:** A single versioned system prompt checked into the repo that encodes the persona (calm, seasoned, non-emotive), preserves the author's core viewpoints, enforces a fixed macro-structure (opening hook → transitions → closing summary), and forbids rewriting technical facts. The prompt is rendered with the article title and metadata, and the cleaned text is passed as the user turn. The prompt file is part of the change; updating it is an explicit change, not a config tweak.

**Rationale:** The brief requires style consistency and fidelity to the author's viewpoints. Pinning the prompt in-repo (with a version number in config for logging) makes reruns reproducible and regressions detectable.

**Alternatives considered:** Multiple persona prompts selected by config (deferred — YAGNI until we have more than one persona), few-shot examples (adds tokens and drift risk; not needed for MVP).

### Decision 5: Semantic chunker, not character chunker

**Choice:** Chunking splits on paragraph boundaries first, then sentence boundaries (using a simple regex sentence splitter tuned for Chinese + English punctuation), and only falls back to hard character cuts if a single sentence exceeds the provider's maximum. Max chunk size is provider-configurable.

**Rationale:** The brief explicitly requires "never split mid-sentence" to keep prosody natural. A pure character-length chunker would break Chinese idioms and English clauses mid-way.

**Alternatives considered:** LLM-based chunker (extra cost and latency for negligible benefit), NLP library (`spaCy`/`jieba`) — deferred; regex gets us 95% of the way for MVP and can be upgraded later behind the same interface.

### Decision 6: TTS concurrency with per-chunk checkpointing

**Choice:** Synthesise chunks concurrently with a configurable pool size (default 4) using `concurrent.futures.ThreadPoolExecutor`. Each chunk's output is written to a per-run cache directory as `chunk_<index>.<ext>`. On retry, existing chunk files are reused. Failed chunks retry up to N times with exponential backoff; permanent failures are recorded in the run log and the chunk is flagged rather than the whole run aborted.

**Rationale:** The brief calls out "synthesis failure auto-retry", "resume without redoing", and "parallel chunk synthesis to cut long-text latency". Threads (not asyncio) are appropriate because TTS calls are I/O-bound and provider SDKs are typically sync-only.

**Alternatives considered:** `asyncio` (forces async SDKs or thread pools anyway), process pool (no CPU work to parallelise, adds IPC cost), redoing everything on failure (fails the "resume" requirement).

### Decision 7: Audio post-production with pydub + ffmpeg

**Choice:** Use `pydub` for concat, fades, and mixing; use a small loudness-normalisation pass (target −16 LUFS integrated, true-peak −1 dBTP) implemented via `ffmpeg` `loudnorm` as a subprocess call (pydub's own normalisation is peak-based and insufficient for podcast standards). Export MP3 at 320 kbps with ID3v2 tags written via `pydub` tag parameters (or `mutagen` if pydub is insufficient).

**Rationale:** `pydub` gives us a clean Python API for the simple operations; `ffmpeg loudnorm` is the industry standard for broadcast-quality loudness and is already a transitive dependency of `pydub`.

**Alternatives considered:** `librosa` (overkill and slow), custom DSP (reinvents the wheel), pydub-only normalisation (fails the brief's "professional audio quality" goal).

### Decision 8: Configuration surface — `.env` for secrets, `config.yaml` for behaviour

**Choice:**

- `.env` holds only secrets + endpoints: `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_BASE_URL`, `TTS_PROVIDER`, `TTS_API_KEY`, `TTS_REGION`, etc. Loaded via `python-dotenv`.
- `config.yaml` (path overridable via `LPM_CONFIG_PATH`) holds all behavioural knobs: cleaning rules, term dictionary, TTS voice + speed + volume, chunk size, concurrency, BGM file path + level, fade durations, output directory + naming pattern, retry counts, log level.
- Config is validated at start-up against a typed schema (dataclasses + a small validator); missing required keys fail fast with a clear message.

**Rationale:** Clean separation of what must be secret from what must be reviewable in source. YAML is friendlier than JSON for human-edited config with comments.

**Alternatives considered:** All-in-`.env` (loses comments, nested structure), TOML (fine but YAML is more familiar to the target audience), Pydantic (fine alternative — noted as a straightforward upgrade path if the dataclass validator grows).

### Decision 9: Stage checkpointing and run log

**Choice:** Each run has a unique `run_id` (timestamp + slug). Under `data/runs/<run_id>/`:

- `article.json`: ingested + cleaned article
- `script.md`: LLM-rewritten script
- `chunks.json`: ordered chunk manifest
- `audio/chunk_*.mp3`: TTS outputs
- `final.mp3`: post-produced result
- `run.log`: structured JSON lines log

The orchestrator checks for each artifact before running its stage; if present and valid, the stage is skipped. A `--force-stage <name>` CLI flag forces re-run from that stage. History (one line per run with status + paths) appends to `data/history.jsonl`.

**Rationale:** Satisfies the "segment-based breakpoint execution" and "single-stage re-run" requirements without introducing a database. Plain files are easy to inspect, diff, and back up.

**Alternatives considered:** SQLite (adds a dependency for negligible MVP benefit), in-memory only with manual copy (fails the resumability requirement).

### Decision 10: Error handling and logging

**Choice:** Use `logging` with a JSON formatter for `run.log` and a human formatter for stderr. All provider calls are wrapped in a retry helper (tenacity-style, but we'll vendor a tiny custom one to avoid an extra dep unless we find we need tenacity). Secrets are redacted by a logging filter that masks any value matching a known secret set.

**Rationale:** Meets "complete exception recording" and "never log secrets" from the brief without pulling in a heavy observability stack.

**Alternatives considered:** `structlog` + `tenacity` (good upgrade path, but not required for MVP).

## Risks / Trade-offs

- [TTS provider outage or rate-limit causing partial failure] → Per-chunk retry with exponential backoff; failed chunks flagged in run log and skipped with silence-placeholder option disabled by default (operator chooses to fill or re-run).
- [LLM rewrites drift from the author's original viewpoints] → Fixed, versioned system prompt with explicit "do not alter technical claims"; prompt version is logged on every run so drift is diffable; optional dry-run mode to print the rewritten script before synthesis.
- [Long articles blow past LLM context window] → Pre-LLM length check; if the cleaned article exceeds a configured token budget, fail fast with a clear message. Multi-segment LLM rewriting is deferred to a later change (explicitly a non-goal of this change).
- [`pydub` + `ffmpeg` binary missing on user machine] → Start-up check that `ffmpeg` is on `PATH`; if not, print install instructions and exit non-zero before any network calls.
- [MP3 loudness inconsistent across episodes] → `ffmpeg loudnorm` two-pass mode; target is pinned in `config.yaml` so all episodes converge on the same integrated loudness.
- [Sensitive article content leaking via third-party APIs] → Call the LLM and TTS only with the text they need; never send the run log or checkpoints; document this clearly in the README.
- [Provider SDK churn breaks one adapter] → Adapter isolation means only that adapter file changes; contract tests per adapter catch regressions before a run.
- [Chinese vs English sentence splitting edge cases in chunker] → Start with a regex tuned for both punctuation sets; accept that some edge cases will be suboptimal in MVP and upgrade to a proper segmenter in a later change without touching the interface.

## Migration Plan

Not applicable — greenfield project. First release is `v0.1.0` corresponding to Sprint 1 scope. Rollback = do not run the tool; no live services are affected.

## Open Questions

- Which LLM provider will be the default in `config.yaml`? (The code supports multiple; picking a default affects the `.env.example`.) — Proposal: leave `LLM_PROVIDER` unset in `.env.example` and document the supported values in the README.
- Which TTS voice will be the default? The brief recommends "calm male" or "news-style male"; the concrete voice ID depends on the chosen TTS vendor. — Proposal: ship voice IDs for each supported vendor in `config.yaml` with the "calm male" equivalent selected per vendor, documented in the README.
- Default BGM: ship a royalty-free track in the repo, or require the user to provide one? — Proposal: require the user to provide one and point to where to drop it; do not ship audio assets in the repo to avoid licensing questions.
