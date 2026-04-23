# Lazy Podcast Mate

[English README](README.md)

一条命令，把原始文章转换为可直接发布的播客 MP3。

输入：你本地磁盘上的 Markdown / TXT / HTML 文章。  
输出：320 kbps MP3，附带正确的 ID3 标签、沉稳旁白音色、背景音乐、淡入淡出，以及符合播客标准的响度（−16 LUFS）。

---

## 环境要求

- Python 3.10 或更高版本
- Poetry
- `ffmpeg` 已加入 `PATH`
  - macOS: `brew install ffmpeg`
  - Ubuntu: `sudo apt install ffmpeg`
  - Windows: <https://ffmpeg.org/download.html>
- 一个 LLM API Key（兼容 OpenAI、Anthropic 或国产商业 LLM）
- 一个 TTS API Key（火山引擎、Azure TTS 或 CosyVoice）

## 安装

```bash
poetry install
```

## 配置

1. 复制密钥模板并填写内容：

   ```bash
   cp .env.example .env
   ```

   编辑 `.env`，设置 `LLM_PROVIDER`、`LLM_API_KEY`、`LLM_MODEL`、`TTS_PROVIDER`、`TTS_API_KEY`。

2. 检查项目根目录下的 `config.yaml`。默认值通常已经够用；大多数情况下你只需要为所选 TTS 提供商设置 `tts.voice_id`。可参考下方的 voice-id 对照表。
   如果你的 LLM 网关在长文章改写时响应较慢，可以调大 `script.request_timeout_seconds`（默认：`180.0`）。如果你的 OpenAI 兼容网关支持 SSE 流式返回，也可以设置 `script.stream: true`，让 `--dry-run-script` 增量输出改写结果。

## 快速开始

首次运行时，可使用如下最小 `.env`（OpenAI + Azure TTS）：

```bash
LLM_PROVIDER=openai_compatible
LLM_API_KEY=sk-...your-openai-key...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
TTS_PROVIDER=azure
TTS_API_KEY=your-azure-speech-key
TTS_REGION=eastus
```

`config.yaml` 最少只需改动语音参数：

```yaml
tts:
  voice_id: zh-CN-YunjianNeural
  rate: 0.92
```

然后执行：

```bash
poetry run lazy-podcast-mate --input examples/sample.md
```

成功后，CLI 会打印最终 MP3 的路径（默认：`data/output/<date>-<slug>.mp3`）。
同时还会生成 `data/output/<date>-<slug>.shownotes.md`，这是一个配套的 markdown 文件，列出原文中的所有链接、代码块、图片和表格（见下方的[非口播内容处理](#非口播内容处理)）。
中间产物（article JSON、script、分块音频、运行日志）会保存在 `data/runs/<run_id>/`。

如果只想预览改写后的脚本而不调用 TTS：

```bash
poetry run lazy-podcast-mate --input examples/sample.md --dry-run-script
```

当 `script.stream: true` 时，OpenAI 兼容提供商会在 `--dry-run-script` 期间将脚本逐步输出到终端，同时仍会把最终整理后的脚本写入 run checkpoint。

如果你希望预览完脚本后继续复用同一份 `script.md`，请在两次命令里显式传入同一个 `--run-id`。否则，不带 `--run-id` 的再次执行会生成一个新的时间戳 run，并重新调用 LLM 生成脚本。

例如，先预览：

```bash
poetry run lazy-podcast-mate --input examples/sample.md --run-id sample-demo --dry-run-script
```

如果生成的口播脚本符合你的要求，再继续运行：

```bash
poetry run lazy-podcast-mate --input examples/sample.md --run-id sample-demo
```

这样第二次运行会复用 `data/runs/sample-demo/script.md`，跳过脚本生成阶段。
这里的 `run_id`，就是 `data/runs/` 下对应的子目录名。

如果你不关心复用之前的脚本，也可以直接运行不带 `--run-id` 的命令：

```bash
poetry run lazy-podcast-mate --input examples/sample.md
```

但这会创建一个新的 run，并再次生成脚本。

## 支持的提供商

### LLM

| `LLM_PROVIDER`      | 必需环境变量                                 | `LLM_MODEL` 示例              |
|---------------------|----------------------------------------------|-------------------------------|
| `openai_compatible` | `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`   | `gpt-4o`                      |
| `anthropic`         | `LLM_API_KEY`, `LLM_MODEL`                   | `claude-3-5-sonnet-20241022`  |
| `domestic`          | `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`   | `qwen-plus`                   |

### TTS

| `TTS_PROVIDER` | 必需环境变量                                     | 说明                                           |
|----------------|--------------------------------------------------|------------------------------------------------|
| `volcano`      | `TTS_API_KEY`, `TTS_APP_ID`, `TTS_CLUSTER`       | 火山引擎（字节跳动）                           |
| `azure`        | `TTS_API_KEY`, `TTS_REGION`                      | `TTS_REGION` 例如 `eastus`                     |
| `cosyvoice`    | `TTS_API_KEY`, `TTS_BASE_URL`                    | 自建或 DashScope 托管的 CosyVoice              |

### 推荐音色（沉稳、阅历感较强的男声）

| Provider  | `tts.voice_id`                        |
|-----------|---------------------------------------|
| volcano   | `zh_male_zhoujielun_emo_v2_mars_bigtts` *(请根据你的音色库调整)* |
| azure     | `zh-CN-YunjianNeural`                 |
| cosyvoice | `longfei` *(或任意类似 "sunwu" / "longjie" 的预设)* |

通过编辑 `config.yaml` 中的 `tts.voice_id` 来切换音色。语速必须保持在 `[0.9, 0.95]` 范围内。

## 非口播内容处理

原始文章里经常包含不适合直接朗读的内容，例如代码块、图片、表格和原始 URL。Lazy Podcast Mate 通过以下两种方式协同处理：

1. **在摄取阶段，将每个可视化元素替换为简短的自然语言占位符**，方便 LLM 决定如何处理：
   - 代码块 → `[此处有一段 Python 代码示例]`
   - Markdown 图片 → `[配图：<alt 文字>]`
   - Markdown 表格 → `[表格：包含 <header 1>、<header 2> 等项对比]`
   - Markdown 链接 `[anchor](url)` → 正文中保留 anchor 文本，URL 被收集到 shownotes 中。

   Prompt **v2**（自 0.2.0 起默认启用）会要求旁白在上下文需要时，用一句简短自然的话描述这些占位符；否则静默省略。LLM 永远不会看到原始代码、URL 或表格分隔符。如果你想复现 0.1.0 的行为，可在 `config.yaml` 中设置 `script.prompt_version: v1`。

2. **输出阶段会生成一个配套的 shownotes 文件**（`<same-stem-as-mp3>.shownotes.md`），把脚本中剥离掉的内容完整展示出来：
   - `## 原文链接 / Links`：按原文顺序列出所有去重后的 URL 及其 anchor 文本。
   - `## 代码片段 / Code snippets`：保留所有 fenced code block 的原始内容和语言标记。
   - `## 配图 / Figures`：以标准 Markdown 图片形式列出所有图片（alt + URL）。
   - `## 表格 / Tables`：原样保留所有 Markdown 表格。

   你可以直接将其粘贴到博客 CMS、播客 feed 描述或单集详情页中。shownotes 的写入是 best-effort：即使失败，MP3 仍然会生成，错误会记录到日志里。

## 常用参数

```bash
poetry run lazy-podcast-mate --input article.md                       # 一次性完整运行
poetry run lazy-podcast-mate --input article.md --dry-run-script      # 只打印改写脚本后停止
poetry run lazy-podcast-mate --input article.md --run-id 2026-04-18-hello   # 继续指定 run
poetry run lazy-podcast-mate --input article.md --force-stage script  # 从 script 阶段开始重新执行
poetry run lazy-podcast-mate --input article.md --lenient             # 某个 chunk 永久失败时继续后续流程
```

## 故障排查

- **找不到 `ffmpeg`**：请先安装（见“环境要求”），然后重新打开 shell。可运行 `ffmpeg -version` 确认。
- **LLM 限流 / 429**：瞬时失败会按指数退避自动重试（见 `config.yaml` 中的 `script.retry`）。如果任务仍失败，请等待后使用相同的 `--run-id` 重新执行，从上一个成功检查点恢复。
- **长文章触发 LLM 读超时**：某些经由网关访问的模型在返回首字节前可能超过一分钟。请在 `config.yaml` 中调大 `script.request_timeout_seconds`（例如 `180` 或 `300`）后重试。
- **开启 streaming 但没有增量输出**：当前只有 `openai_compatible` / `domestic` 提供商会走新的 SSE 流式路径。请确认已设置 `script.stream: true`，并且你的网关支持 `stream: true`。
- **严格模式下 TTS chunk 永久失败**：任务会中止。打开 `data/runs/<run_id>/run.log`（JSON lines）查看失败的 chunk 索引和提供商错误信息。修复或缩短 `data/runs/<run_id>/chunks.json` 中对应 chunk 的文本后，再用相同的 `--run-id` 重试。
- **宽松模式下 TTS chunk 永久失败**：添加 `--lenient`，系统会在 `run.log` 中标记该 chunk 并继续执行。最终 MP3 在该 chunk 位置会有空白。
- **恢复失败的运行**：传入 `--run-id <id>`（run 启动时会打印，`data/runs/` 下也可见）。已完成的阶段会自动跳过，只重做未完成部分。
- **强制重跑某个阶段**：`--force-stage <stage>` 会丢弃从该阶段开始的所有检查点并重新执行。可用阶段：`ingestion`、`cleaning`、`script`、`chunking`、`tts`、`post`、`output`。
- **响度不达标**：`ffmpeg loudnorm` 目标为 −16 LUFS ±1 LU（可通过 `post.loudness_tolerance_lu` 配置）。若校验失败，流水线会中止。只有在明确原因的情况下才建议放宽容差。
- **输出码率低于 320 kbps**：流水线会拒绝输出该节目。请检查 `ffprobe` 是否在 PATH 中，以及源音频分块是否能正常解码。
- **Python 3.13+ 下的 `pydub` 错误**：`pydub` 依赖已在 Python 3.13 标准库中移除的 `audioop` 模块。请安装 `audioop-lts`（已包含在 `requirements.txt` 中）。
- **LLM 返回 `'temperature' is deprecated for this model`**：某些推理型模型（Anthropic `claude-opus-4-7`、OpenAI `o1` / `o3` 以及对应别名）会拒绝 `temperature`、`top_p` 和 `max_tokens`。请在 `config.yaml` 的 `script:` 下将它们设为 `null`，适配器会从请求体中移除这些字段。默认值（`temperature: 0.5`）仍适用于 `gpt-4o`、`claude-3.5-sonnet` 等标准聊天模型。
- **Azure TTS 对每个 chunk 都返回空响应的 HTTP 400**：通常是因为 (a) `tts.voice_id` 为空或非法，或 (b) 语音的 BCP-47 locale 与 SSML 不匹配。加载器现在会在 `voice_id` 为空时快速失败，适配器也会在错误信息里暴露 Azure 的诊断响应头（`X-Microsoft-Reason`、`X-RequestId`）以及发出的 SSML。请从 README 的“推荐音色”表中选择合法音色（例如 `zh-CN-YunjianNeural`）；适配器会根据 voice id 推断 `xml:lang`。
- **`could not find loudnorm JSON in ffmpeg output`**：ffmpeg 必须以 `-loglevel info` 或更高等级运行，`loudnorm` 滤镜才会输出统计块；当前 runner 已自动这样做。如果仍报错，请确认你的 ffmpeg 构建包含 `loudnorm` 滤镜（`ffmpeg -filters 2>&1 \| grep loudnorm`）。另外，如果后处理输入音频实质上是静音（全零采样），`loudnorm` 会测得 `input_i = "-inf"`；当前流水线会识别这种情况，直接返回原音频，并在 `run.log` 中记录 `WARNING`，而不会失败。

## 项目结构

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

## 许可证

Apache License 2.0。详见 [LICENSE](LICENSE)。
