# Lazy Podcast Mate

Turn an original article into a publish-ready podcast MP3 with a single command.

Input: a Markdown / TXT / HTML article on your disk.
Output: a 320 kbps MP3 with correct ID3 tags, calm-narrator voice, BGM, fades, and podcast-standard loudness (−16 LUFS).

---

## Requirements

- Python 3.10 or newer
- `ffmpeg` on your `PATH`
  - macOS:   `brew install ffmpeg`
  - Ubuntu:  `sudo apt install ffmpeg`
  - Windows: <https://ffmpeg.org/download.html>
- One LLM API key (OpenAI-compatible, Anthropic, or a domestic commercial LLM)
- One TTS API key (Volcano Engine, Azure TTS, or CosyVoice)

## Install

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

## Configure

1. Copy the secrets template and fill it in:

    ```bash
    cp .env.example .env
    ```

    Edit `.env` — set `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`, `TTS_PROVIDER`, `TTS_API_KEY`.

2. Review `config.yaml` at the project root. The defaults are sensible; you mostly only need to set `tts.voice_id` for your chosen TTS provider. See the voice-ID reference below.

## Quick start

Minimal `.env` for a first run with OpenAI + Azure TTS:

```bash
LLM_PROVIDER=openai_compatible
LLM_API_KEY=sk-...your-openai-key...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
TTS_PROVIDER=azure
TTS_API_KEY=your-azure-speech-key
TTS_REGION=eastus
```

Minimum `config.yaml` tweak (just set the voice):

```yaml
tts:
  voice_id: zh-CN-YunjianNeural
  rate: 0.92
```

Then run:

```bash
lazy-podcast-mate --input examples/sample.md
```

On success the CLI prints the path to the final MP3 (default: `data/output/<date>-<slug>.mp3`).
Alongside it you also get `data/output/<date>-<slug>.shownotes.md` — a companion markdown file listing every link, code block, figure, and table from the source article (see [Handling non-spoken content](#handling-non-spoken-content) below).
Intermediate artefacts (article JSON, script, per-chunk audio, run log) live under `data/runs/<run_id>/`.

To preview the rewritten script without calling TTS:

```bash
lazy-podcast-mate --input examples/sample.md --dry-run-script
```

## Supported providers

### LLM

| `LLM_PROVIDER`      | Required env vars                            | Example `LLM_MODEL`           |
|---------------------|----------------------------------------------|-------------------------------|
| `openai_compatible` | `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`   | `gpt-4o`                      |
| `anthropic`         | `LLM_API_KEY`, `LLM_MODEL`                   | `claude-3-5-sonnet-20241022`  |
| `domestic`          | `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`   | `qwen-plus`                   |

### TTS

| `TTS_PROVIDER` | Required env vars                                | Notes                                          |
|----------------|--------------------------------------------------|------------------------------------------------|
| `volcano`      | `TTS_API_KEY`, `TTS_APP_ID`, `TTS_CLUSTER`       | Volcano Engine (字节跳动)                      |
| `azure`        | `TTS_API_KEY`, `TTS_REGION`                      | `TTS_REGION` e.g. `eastus`                     |
| `cosyvoice`    | `TTS_API_KEY`, `TTS_BASE_URL`                    | Self-hosted or DashScope-hosted CosyVoice      |

### Recommended voices (calm, seasoned male)

| Provider  | `tts.voice_id`                        |
|-----------|---------------------------------------|
| volcano   | `zh_male_zhoujielun_emo_v2_mars_bigtts` *(adjust to your voice library)* |
| azure     | `zh-CN-YunjianNeural`                 |
| cosyvoice | `longfei` *(or any "sunwu"/"longjie"-style preset)* |

Change the voice by editing `tts.voice_id` in `config.yaml`. Speaking rate must stay within `[0.9, 0.95]`.

## Handling non-spoken content

Source articles routinely contain elements that make no sense when read aloud — fenced code blocks, images, tables, and raw URLs. Lazy Podcast Mate handles them in two complementary ways:

1. **Ingestion replaces each visual element with a short natural-language placeholder** the LLM can read and decide what to do with:
   - Fenced code block → `[此处有一段 Python 代码示例]`
   - Markdown image → `[配图：<alt 文字>]`
   - Markdown table → `[表格：包含 <header 1>、<header 2> 等项对比]`
   - Markdown link `[anchor](url)` → the anchor text stays in the body, the URL is harvested for show notes.

   Prompt **v2** (the default since 0.2.0) instructs the narrator to either describe the placeholder in one short sentence when the surrounding sentences depend on it, or drop it silently. The LLM never sees the raw code, URLs, or table bars. Set `script.prompt_version: v1` in `config.yaml` to reproduce the 0.1.0 behaviour.

2. **The output stage writes a companion show-notes file** (`<same-stem-as-mp3>.shownotes.md`) that surfaces everything the script stripped out:
   - `## 原文链接 / Links` — every unique URL with its anchor text, in source order.
   - `## 代码片段 / Code snippets` — every fenced code block, preserved verbatim with its original language tag.
   - `## 配图 / Figures` — every image as a standard markdown image (alt + URL).
   - `## 表格 / Tables` — every markdown table, preserved verbatim.

   Paste this straight into your blog CMS, feed description, or episode page. Show-notes writing is best-effort: if it fails, the MP3 is still delivered and the error is logged.

## Common flags

```bash
lazy-podcast-mate --input article.md                       # one-shot run
lazy-podcast-mate --input article.md --dry-run-script      # print rewritten script and stop
lazy-podcast-mate --input article.md --run-id 2026-04-18-hello   # resume a specific run
lazy-podcast-mate --input article.md --force-stage script  # redo from the script stage down
lazy-podcast-mate --input article.md --lenient             # keep going past a permanently-failed chunk
```

## Troubleshooting

- **`ffmpeg` not found** — install it (see Requirements) and reopen your shell. Run `ffmpeg -version` to confirm.
- **LLM rate-limit / 429** — transient failures are retried with exponential backoff (see `script.retry` in `config.yaml`). If the run still fails, wait and re-run with the same `--run-id` to resume from the last good checkpoint.
- **TTS chunk permanent failure in strict mode** — the run aborts. Open `data/runs/<run_id>/run.log` (JSON lines) to find the offending chunk index and the provider's error message. Fix or shorten the chunk's text in `data/runs/<run_id>/chunks.json`, then re-run with the same `--run-id`.
- **TTS chunk permanent failure in lenient mode** — pass `--lenient` to flag the chunk in `run.log` and keep going. The final MP3 will have a gap where that chunk would have been.
- **Resuming a failed run** — pass `--run-id <id>` (the ID is printed at run start and appears in `data/runs/`). Completed stages are skipped automatically; only unfinished work is re-done.
- **Forcing a stage** — `--force-stage <stage>` discards all checkpoints from that stage onward and re-runs. Stages: `ingestion`, `cleaning`, `script`, `chunking`, `tts`, `post`, `output`.
- **Loudness off target** — `ffmpeg loudnorm` targets −16 LUFS ±1 LU (configurable via `post.loudness_tolerance_lu`). If the verification fails, the pipeline aborts; widen the tolerance only if you understand why.
- **Output bitrate below 320 kbps** — the pipeline refuses to ship the episode. Check `ffprobe` is on PATH and that your source chunks decode cleanly.
- **Python 3.13+ pydub error** — `pydub` depends on the removed-in-3.13 `audioop` stdlib module. Install `audioop-lts` (already in `requirements.txt`).
- **LLM returns `'temperature' is deprecated for this model`** — some reasoning-tier models (Anthropic `claude-opus-4-7`, OpenAI `o1`/`o3`, Zoom LLM gateway aliases of those) reject `temperature`, `top_p`, and `max_tokens`. Set them to `null` in `config.yaml` under `script:` — the adapter will drop the field from the request body. Defaults (`temperature: 0.5`) still work for standard chat models like `gpt-4o` or `claude-3.5-sonnet`.
- **Azure TTS returns HTTP 400 with an empty body for every chunk** — almost always caused by (a) an empty or invalid `tts.voice_id`, or (b) a voice whose BCP-47 locale doesn't match the SSML. The loader now fails fast on empty `voice_id`, and the adapter surfaces Azure's diagnostic headers (`X-Microsoft-Reason`, `X-RequestId`) plus the outgoing SSML in the error message. Pick a voice from the README's "Recommended voices" table (e.g. `zh-CN-YunjianNeural`); the adapter infers `xml:lang` from the voice id.
- **`could not find loudnorm JSON in ffmpeg output`** — ffmpeg must be run with `-loglevel info` or higher for the `loudnorm` filter's stats block to be emitted; the runner does this automatically. If you still see this error, check that your ffmpeg build has the `loudnorm` filter (`ffmpeg -filters 2>&1 \| grep loudnorm`). Separately, if the input to post-production is effectively silent (all-zero samples), loudnorm measures `input_i = "-inf"`; the pipeline now detects this and returns the audio unchanged with a `WARNING` in `run.log` rather than failing.

## Layout

```
lazy_podcast_mate/
  ingestion/    # md/txt/html readers -> Article
  cleaning/     # whitespace, term dictionary
  script/       # LLM providers + versioned prompt
  chunking/     # sentence-aware splitter
  tts/          # volcano / azure / cosyvoice adapters
  post/         # concat / fade / bgm / loudnorm / export
  output/       # id3, filename, history
  orchestrator/ # runner, checkpoints, run log
  config/       # env + yaml loader, validation
  cli.py
```

## License

MIT.
