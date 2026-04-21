# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
follows [Semantic Versioning](https://semver.org/).

## [0.2.0] — 2026-04-19

### Added

- **Placeholder-based handling of non-spoken content.** Ingestion now detects fenced code blocks, Markdown images, and Markdown tables and replaces each with an opaque `[[LPM:<kind>:<n>]]` token plus a `PlaceholderRef` record (kind, human label, raw detail). The cleaner substitutes the token with a short natural-language label (e.g. `[此处有一段 Python 代码示例]`, `[配图：AWS 架构图]`, `[表格：包含 Provider、Free tier 等项对比]`) before the text reaches the LLM. Raw code / URLs / table bars never appear in the prompt.
- **Inline-link harvesting.** Every `[anchor](url)` in Markdown input is collected into `Article.links` (deduped by URL). The anchor text stays in the spoken body; the URL is dropped from the script and surfaced via show notes.
- **Prompt v2** (`script/prompts/v2.md`, now the default) with explicit rules for reading / dropping `[此处有...]` placeholders and stricter anti-hype guidance. Existing runs that pin `script.prompt_version: v1` keep the 0.1.0 behaviour.
- **Show-notes companion file.** The output stage now writes `<stem>.shownotes.md` next to the final MP3, containing a link list, every code snippet (verbatim), every figure (as markdown images), and every table (verbatim). Writing show notes is best-effort and never aborts the run.
- `Article.links` and `Article.placeholders` are serialised into the per-run `article.json` checkpoint, so show notes reproduce correctly on resume.
- New unit tests: ingestion placeholders / link dedup / table summary, cleaner label substitution and orphan-token scrubbing, show-notes rendering and on-existing handling (15 new tests total).

### Changed

- Default `script.prompt_version` is now `v2` for new installs. Existing `config.yaml` files with `prompt_version: v1` continue to work unchanged.

## [0.1.0] — 2026-04-18

First release — Sprint 1 scope of `init-article-to-podcast-pipeline`.

### Added

- End-to-end CLI pipeline: **Markdown / TXT / HTML article → 320 kbps podcast MP3** in one command (`lazy-podcast-mate --input <file>`).
- Four-layer modular package (`ingestion`, `cleaning`, `script`, `chunking`, `tts`, `post`, `output`, `orchestrator`, `config`).
- Pluggable LLM providers for script rewriting: `openai_compatible`, `anthropic`, `domestic`.
- Pluggable TTS providers: Volcano Engine, Azure TTS, CosyVoice. Concurrency configurable per run.
- Versioned "calm, seasoned narrator" system prompt (`script/prompts/v1.md`) with fixed intro → transitions → closing structure and a post-process pass that strips emoji and consecutive exclamation marks.
- Semantic text chunker (paragraph → sentence, hard-split as last resort) with stable, hashed chunk manifest.
- `pydub` + `ffmpeg` audio post-production: concat with inter-chunk silence, optional `afftdn` denoise, two-pass `loudnorm` targeting −16 LUFS / −1 dBTP, optional BGM mix at 10–15% RMS ratio, configurable fades, 320 kbps CBR MP3 export with bitrate verification.
- ID3v2 tagging (title, artist, album, release date, run-id comment) on every exported MP3.
- Checkpoint + resume: every stage writes a durable artefact to `data/runs/<run_id>/`, so a mid-run failure can be continued with `--run-id` and no stage is re-done unnecessarily.
- JSON-lines `run.log` per run plus `data/history.jsonl` for every run's summary.
- Env-only secrets with a logging filter that masks them from stderr and `run.log`; `config.yaml` is rejected if it contains any key that looks like a secret.
- `.env.example`, default `config.yaml`, `examples/sample.md`, and a full README.

### Known issues / deferred

- Feishu (Lark) document webhook ingestion — planned for Sprint 3.
- RSS feed generation and multi-platform auto-distribution — planned for Sprint 3.
- Voice cloning and multi-speaker dialogues — out of scope for 0.x.
