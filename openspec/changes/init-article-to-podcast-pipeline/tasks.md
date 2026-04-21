## 1. Project scaffolding and tooling

- [x] 1.1 Create the `lazy_podcast_mate/` package with empty `__init__.py` files for `ingestion`, `cleaning`, `script`, `chunking`, `tts`, `post`, `output`, `orchestrator`, and `config` subpackages
- [x] 1.2 Add `requirements.txt` pinning `python-dotenv`, `pydub`, `requests`, `pyyaml`, and test deps (`pytest`, `pytest-mock`), with a comment noting `ffmpeg` is a required system dependency
- [x] 1.3 Add `.env.example` listing every supported env var (`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `TTS_PROVIDER`, `TTS_API_KEY`, `TTS_REGION`) with no real values
- [x] 1.4 Add a default `config.yaml` at the project root with commented sections for cleaning, chunking, TTS, post-production, output, and logging
- [x] 1.5 Add `pyproject.toml` (or `setup.cfg`) declaring the console entry point `lazy-podcast-mate = lazy_podcast_mate.cli:main`
- [x] 1.6 Add `README.md` with install steps, `ffmpeg` prerequisite, `.env` setup, config overview, quick-start command, and a link to an `examples/` folder
- [x] 1.7 Add an `examples/` folder with one sample Markdown article suitable for a 2–5 minute episode
- [x] 1.8 Add `.gitignore` covering `.env`, `data/runs/`, `data/history.jsonl`, `__pycache__`, and virtualenv folders

## 2. Configuration layer

- [x] 2.1 Implement `config/env.py` that loads `.env` via `python-dotenv` and exposes typed accessors for every secret/endpoint
- [x] 2.2 Implement `config/schema.py` defining typed dataclasses for the YAML schema (cleaning rules, term dictionary, chunking, TTS voice/rate/volume/concurrency, post-production fades + BGM + loudness target, output directory + filename pattern + `on_existing` policy, retry budgets, log level)
- [x] 2.3 Implement `config/loader.py` that merges env + YAML, validates against the schema, and raises a `ConfigError` listing every missing/invalid key at once
- [x] 2.4 Reject secrets found in `config.yaml` (keys matching `api_key`, `token`, `secret`, `password`) at load time with a clear message
- [x] 2.5 Implement a logging filter in `config/logging.py` that masks every value present on the env-var secret allowlist
- [x] 2.6 Unit-test the loader: missing required key fails fast, env-only secrets, `LPM_CONFIG_PATH` override works, secret in YAML is rejected, redaction filter masks keys

## 3. Article ingestion

- [x] 3.1 Define the `Article` dataclass in `ingestion/models.py` with `title`, `body`, `source_path`, `source_format`, `detected_encoding`
- [x] 3.2 Implement encoding detection with a UTF-8 preference and a safe fallback, rejecting undecodable input with a clear error
- [x] 3.3 Implement `ingestion/markdown.py` that extracts H1 title and paragraph body, strips fenced and inline code, flattens inline markup, and removes image/link markup leaving visible text
- [x] 3.4 Implement `ingestion/html.py` that uses `html.parser` (stdlib) to strip `<script>`, `<style>`, `<nav>`, and other non-content elements, extracting `<title>` or first `<h1>` and visible `<body>` text
- [x] 3.5 Implement `ingestion/text.py` for `.txt` inputs, treating the first short non-empty line as title and the rest as body
- [x] 3.6 Implement `ingestion/loader.py` that dispatches by extension, enforces a configured max file size, rejects empty input, and returns an `Article`
- [x] 3.7 Unit-test each reader with fixture files covering happy paths, empty input, unsupported extension, undecodable bytes, and stripping of code/markup

## 4. Text cleaning

- [x] 4.1 Implement `cleaning/whitespace.py` that collapses whitespace and paragraph breaks and repairs mid-sentence line breaks
- [x] 4.2 Implement `cleaning/terms.py` applying the configured term dictionary with per-entry case-sensitivity and word-boundary rules
- [x] 4.3 Implement `cleaning/cleaner.py` composing the above into a single `clean(article, config) -> str` function and ensure the output is deterministic for the same input+config
- [x] 4.4 Unit-test: whitespace collapse, mid-sentence repair, term substitution applied/not applied, empty dictionary no-op, determinism check (run twice, compare bytes)

## 5. Script rewriting (LLM)

- [x] 5.1 Define the `ScriptRewriter` Protocol in `script/base.py` with `rewrite(cleaned_text: str, *, metadata) -> str`
- [x] 5.2 Add the versioned system prompt to `script/prompts/v1.md` encoding the calm-seasoned persona, fixed macro-structure (intro → transitions → closing), and "do not alter technical claims" constraint
- [x] 5.3 Implement `script/prompt_builder.py` that loads the versioned prompt and renders it with article metadata
- [x] 5.4 Implement `script/openai_compatible.py` adapter using `requests` against a configurable base URL and model
- [x] 5.5 Implement `script/anthropic.py` adapter
- [x] 5.6 Implement `script/domestic.py` adapter for at least one domestic commercial LLM supported by the brief
- [x] 5.7 Implement `script/registry.py` mapping `LLM_PROVIDER` to a factory
- [x] 5.8 Implement a token-budget pre-check that fails fast with a clear message when cleaned input exceeds the configured budget
- [x] 5.9 Wrap provider calls with a retry helper (exponential backoff, configurable max attempts, retries only on network / 5xx / 429)
- [x] 5.10 Emit a structured log entry with `prompt_version`, `provider`, `model` on every successful call
- [x] 5.11 Post-process: strip emojis and consecutive `!`/`！` runs to enforce persona tone
- [x] 5.12 Unit-test with a fake provider: happy path, retries on transient failure then succeeds, exceeds retry budget fails the run, token-budget exceeded fails fast, emoji/exclamation stripping works

## 6. Text chunking

- [x] 6.1 Implement a sentence splitter in `chunking/sentences.py` tuned for Chinese (`。！？；…`) and English (`.!?;`) punctuation, preserving terminators
- [x] 6.2 Implement `chunking/chunker.py` that groups paragraphs first, then sentences, up to a configured max char count, and performs a hard character split only when a single sentence exceeds the limit (with a logged warning)
- [x] 6.3 Emit `TextChunk` records with `index`, `text`, `char_count`, and a stable `hash`
- [x] 6.4 Serialise the ordered manifest to `chunks.json` in the run directory
- [x] 6.5 Unit-test: paragraph-aligned chunks, sentence-aligned split of an oversized paragraph, hard-split of an oversized sentence emits a warning, manifest serialisation round-trips

## 7. TTS synthesis

- [x] 7.1 Define the `TTSSynthesizer` Protocol in `tts/base.py` with `synthesize(chunk, voice) -> bytes`, a `supports_concurrency: int` attribute, and an `audio_format` attribute (`mp3` or `wav`)
- [x] 7.2 Implement `tts/volcano.py` (Volcano Engine) adapter
- [x] 7.3 Implement `tts/azure.py` (Azure TTS) adapter
- [x] 7.4 Implement `tts/cosyvoice.py` adapter
- [x] 7.5 Implement `tts/registry.py` mapping `TTS_PROVIDER` to a factory
- [x] 7.6 Validate voice config at start-up: reject speaking rate outside 0.9–0.95 with a clear error
- [x] 7.7 Implement `tts/synthesizer.py` that runs chunks through a `ThreadPoolExecutor` sized from config, writes each chunk to `audio/chunk_<index>.<ext>`, and reuses existing files on rerun
- [x] 7.8 Implement per-chunk retry with exponential backoff (transient: network/429/5xx) up to the configured per-chunk budget
- [x] 7.9 Implement strict vs lenient failure modes: strict aborts the run on permanent failure; lenient flags the chunk in `run.log` and continues
- [x] 7.10 Unit-test with a fake TTS provider: happy path writes all files, rerun reuses cached files, transient failure retries then succeeds, permanent failure aborts in strict mode, permanent failure flags-and-continues in lenient mode

## 8. Audio post-production

- [x] 8.1 Implement `post/ffmpeg_check.py` that verifies `ffmpeg` is on `PATH` at start-up and exits non-zero with install instructions if missing
- [x] 8.2 Implement `post/concat.py` using `pydub` to concatenate chunk audio files in manifest order with a configured inter-chunk silence
- [x] 8.3 Implement `post/fades.py` applying configured fade-in and fade-out (default 500 ms each)
- [x] 8.4 Implement `post/denoise.py` applying a light noise-reduction pass on the voice track (via an `ffmpeg` `afftdn` or equivalent subprocess call)
- [x] 8.5 Implement `post/loudnorm.py` running `ffmpeg` two-pass `loudnorm` targeting integrated −16 LUFS with a −1 dBTP ceiling and verifying the measured result is within ±1 LU
- [x] 8.6 Implement `post/bgm.py` that mixes an optional BGM below the voice at 10–15% RMS ratio, looping or trimming to match the voice duration, rejecting ratios outside the allowed range
- [x] 8.7 Implement `post/export.py` exporting the final audio as a 320 kbps CBR MP3 (44.1 or 48 kHz stereo) and failing if the actual encoded bitrate differs
- [x] 8.8 Unit-test (with small synthetic wavs): concat duration equals sum + silences, fades applied, BGM RMS ratio within bounds, loudness within ±1 LU of target, export rejects non-320 kbps results, missing ffmpeg exits early

## 9. Output management

- [x] 9.1 Implement `output/id3.py` writing `title`, `artist`, `album`, `date`, `comment` ID3v2 tags on the exported MP3 from config + article metadata
- [x] 9.2 Implement `output/filename.py` rendering the configured filename pattern (default `{date}-{slug}.mp3`) with a safe slug transformation
- [x] 9.3 Implement `output/writer.py` placing the final MP3 in the configured output directory with an `on_existing` policy (`error` | `suffix`); never silently overwrite
- [x] 9.4 Implement `output/history.py` appending one JSON line per run to `data/history.jsonl` with `run_id`, `source_path`, `output_path`, `status`, timestamps, duration, providers, and error summary
- [x] 9.5 Unit-test: ID3 tags round-trip, filename slug for ASCII + Chinese titles, `on_existing=error` refuses to overwrite, `on_existing=suffix` appends `-1`, history line appended on both success and failure

## 10. Orchestration and CLI

- [x] 10.1 Implement `orchestrator/runid.py` generating a stable `run_id` from timestamp + article slug
- [x] 10.2 Implement `orchestrator/checkpoints.py` defining the artefact contract per stage (ingestion → `article.json`, cleaning → embedded in `article.json`, script → `script.md`, chunking → `chunks.json`, TTS → `audio/chunk_*.*`, post → `final.mp3`, output → entry in `history.jsonl`) and a `has_valid_checkpoint(stage)` check
- [x] 10.3 Implement `orchestrator/runner.py` that executes stages in order, skipping stages whose checkpoints exist and validate, and re-running any stage whose checkpoint is missing or invalidated
- [x] 10.4 Implement `orchestrator/logger.py` writing JSON-lines entries to `data/runs/<run_id>/run.log` and a human-readable line to stderr for stage start/end
- [x] 10.5 Implement `cli.py` with `argparse` supporting `--input <path>`, `--config <path>`, `--run-id <id>` (resume), `--force-stage <name>`, `--lenient` / `--strict`, `--dry-run-script` (print rewritten script and stop), and `--verbose`
- [x] 10.6 Wire the CLI entry point: load config → verify `ffmpeg` → verify providers reachable (cheap no-op call or config validation only) → run pipeline → print final MP3 path on success, or failing stage + path to `run.log` on failure
- [x] 10.7 Integration-test with fake LLM + fake TTS + a real tiny BGM fixture: full end-to-end run produces an MP3 with correct ID3 tags; rerun with one chunk audio deleted only re-synthesises that chunk; `--force-stage script` re-runs everything from the script stage down

## 11. Documentation and examples

- [x] 11.1 Expand `README.md` with a worked example: `.env` values to set, `config.yaml` minimal edits, command to run against `examples/sample.md`, expected output location
- [x] 11.2 Document every supported LLM provider value and TTS provider value, including the expected env vars per provider
- [x] 11.3 Document per-provider voice ID examples for the "calm, seasoned male" persona and how to change voices via `config.yaml`
- [x] 11.4 Document troubleshooting: `ffmpeg` missing, LLM rate-limit, TTS chunk permanent failure, how to rerun a failed run, how to force a single stage
- [x] 11.5 Add a CHANGELOG entry for `v0.1.0` corresponding to Sprint 1 scope

## 12. Verification

- [x] 12.1 Run `pytest` with all unit and integration tests green — 68 passed, 9 skipped (ffmpeg-dependent; unblocked once the user installs ffmpeg locally)
- [ ] 12.2 Manual end-to-end run on the `examples/sample.md` article using a real LLM and real TTS provider; confirm the final MP3 is 320 kbps, has correct ID3 tags, and its integrated loudness is within ±1 LU of −16 LUFS **— requires user-supplied API keys + ffmpeg; deferred to user acceptance**
- [ ] 12.3 Kill the pipeline mid-TTS, restart with the same `run_id`, and confirm only missing chunks are re-synthesised **— requires 12.2 environment; deferred to user acceptance**
- [ ] 12.4 Confirm no secrets appear in `run.log` or stderr across the above runs **— deferred to user acceptance; automated test `tests/test_config.py::test_secret_redaction_masks_values_in_logs` already exercises the redactor**
- [x] 12.5 Run `openspec status --change init-article-to-podcast-pipeline` and confirm every artifact reports `done` — reported `Progress: 4/4 artifacts complete`
