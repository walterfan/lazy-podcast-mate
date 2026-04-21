## Why

Independent technical writers and podcasters waste hours manually converting written articles into podcast episodes: rewriting prose into spoken form, running synthesis, editing audio, adding BGM, normalising loudness, and exporting a distribution-ready MP3. No existing tool chains these steps together with a locally runnable, modular Python pipeline that produces a professional-sounding, stylistically consistent podcast from a single article input. Lazy Podcast Mate closes that gap so a creator can go from an original article to a publish-ready MP3 with no manual intervention.

## What Changes

- Introduce a new Python 3.10+ project `lazy-podcast-mate` with a four-layer architecture: input ingestion, core processing, audio generation, output management.
- Add a unified CLI entry point that runs the full pipeline: article → cleaned text → LLM-rewritten spoken script → semantic chunks → TTS audio segments → post-produced MP3 with BGM, fades, loudness normalisation, and ID3 metadata.
- Support Markdown, plain text, and HTML article inputs from the local filesystem, with automatic title/body extraction and noise filtering (code blocks, markup, control chars).
- Integrate pluggable LLM providers (OpenAI-compatible, Anthropic, and domestic commercial LLMs) behind a standard `ScriptRewriter` interface, with a fixed prompt contract that preserves the author's core viewpoints and enforces a calm, seasoned narrator persona.
- Integrate pluggable TTS providers (Volcano Engine, Azure TTS, CosyVoice) behind a standard `TTSSynthesizer` interface, with per-provider voice/speed/volume configuration, chunk-level retry, and resume-from-checkpoint behaviour.
- Add audio post-production using `pydub` + `ffmpeg`: segment concatenation, fade-in/fade-out, optional BGM mixing at 10–15% of vocal level, noise reduction, and peak/loudness normalisation; export 320 kbps MP3 with ID3 tags (title, author, date).
- Add stage-level checkpointing so any failed stage can be re-run independently without redoing earlier work, plus a structured run log for observability.
- Add a `.env`-driven configuration layer (API keys, endpoints, defaults) and a `config.yaml`-style business config (cleaning rules, term dictionary, TTS parameters, BGM rules, output paths, naming).
- Ship `requirements.txt`, an `.env.example` template, a quick-start `README`, and a runnable `examples/` input so a new user can produce their first episode on a stock laptop.
- **Non-goals for this change**: Feishu webhook ingestion, RSS feed generation, multi-platform auto-distribution, and UI — these are captured as follow-up sprints (Sprint 2 and 3) and are explicitly out of scope.

## Capabilities

### New Capabilities

- `article-ingestion`: Read Markdown/TXT/HTML articles from local paths, extract title + body, strip code/markup/noise, reject empty or mojibake input, and emit a normalised `Article` record for downstream stages.
- `text-cleaning`: Apply rule-based and dictionary-based cleaning to the normalised article — collapse whitespace, fix sentence boundaries, apply user-defined term substitutions, and produce speakable prose.
- `script-rewriting`: Call a pluggable LLM provider with a fixed persona prompt (calm, seasoned, non-emotive) to restructure the cleaned text into a podcast script with opening, transitions, and closing, while preserving the author's core viewpoints.
- `text-chunking`: Split the rewritten script into TTS-sized chunks along sentence/paragraph boundaries without cutting mid-sentence, and emit ordered chunks suitable for parallel synthesis.
- `tts-synthesis`: Synthesise each chunk via a pluggable TTS provider with configurable voice/speed/volume, retry failed chunks, skip/flag unrecoverable ones, and cache results on disk for resumability.
- `audio-post-production`: Concatenate synthesised chunks, apply fade in/out, optionally mix BGM at a configured ratio, run noise reduction and loudness normalisation, and export a single 320 kbps MP3.
- `output-management`: Write ID3 metadata (title, author, date), place the MP3 in a configured output path with a deterministic filename, and append a structured entry to the run history log.
- `pipeline-orchestration`: Drive stages in order, persist per-stage checkpoints, surface progress + errors via a structured log, and support re-running a single failed stage.
- `configuration`: Load secrets from `.env` and business parameters from a central config file; validate required keys at start-up; never log secrets.

### Modified Capabilities

<!-- None — this is a greenfield project. -->

## Impact

- New code: full `lazy-podcast-mate` Python package (ingestion, cleaning, script, chunking, TTS, post, output, orchestration, config modules) plus CLI entry point and tests.
- New dependencies: `python-dotenv`, `pydub`, `requests`, `pyyaml`, plus an LLM SDK and a TTS SDK per configured provider; system dependency on `ffmpeg`.
- New config surface: `.env` (API keys/endpoints), `config.yaml` (cleaning rules, term dictionary, TTS params, BGM rules, output paths), and a `data/` tree for checkpoints and history.
- Platforms: Windows, macOS, Linux; no GPU required.
- External services: one LLM API and one TTS API are mandatory at runtime; secrets are provided via environment variables only.
- Out of scope / deferred: Feishu auto-ingest, RSS feed, multi-platform distribution, and any UI — tracked for future changes, not this one.
