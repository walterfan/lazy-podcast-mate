## ADDED Requirements

### Requirement: Read articles from supported local formats

The system SHALL accept a local file path pointing to a Markdown (`.md`, `.markdown`), plain text (`.txt`), or HTML (`.html`, `.htm`) file and produce a normalised `Article` record containing `title`, `body`, `source_path`, `source_format`, and `detected_encoding`.

#### Scenario: Markdown article is ingested

- **WHEN** the user runs the pipeline with a `.md` file that has an H1 title and paragraph body
- **THEN** the system extracts the H1 text as `title`, the remaining prose as `body`, sets `source_format` to `markdown`, and emits an `Article` record downstream

#### Scenario: HTML article is ingested

- **WHEN** the user runs the pipeline with an `.html` file
- **THEN** the system extracts the `<title>` (or first `<h1>`) as `title` and the rendered text content of `<body>` as `body`, with script, style, and nav elements removed

#### Scenario: Plain text article is ingested

- **WHEN** the user runs the pipeline with a `.txt` file whose first non-empty line is short
- **THEN** the system treats the first non-empty line as `title` and the remainder as `body`

### Requirement: Strip non-spoken content during ingestion

The system SHALL remove content that cannot be spoken aloud — fenced code blocks, inline code, Markdown/HTML tags, image/link markup leaving only the visible text, and control characters — before emitting the `Article` record.

#### Scenario: Markdown with code blocks is cleaned

- **WHEN** the input contains a fenced ```python ... ``` block
- **THEN** the emitted `Article.body` does not contain the code block or its fence markers

#### Scenario: Inline Markdown markup is flattened

- **WHEN** the input contains `**bold**`, `_italic_`, `` `code` ``, and `[link text](https://example.com)`
- **THEN** the emitted `Article.body` contains only `bold`, `italic`, and `link text` with the code and URL removed

### Requirement: Reject invalid input

The system SHALL fail fast with a clear, actionable error when the input file is empty, larger than a configured maximum, has an unsupported extension, or cannot be decoded as text.

#### Scenario: Empty file is rejected

- **WHEN** the input file has zero bytes or contains only whitespace
- **THEN** the system exits non-zero with a message identifying the file and the reason `empty input`, and no downstream stage runs

#### Scenario: Unsupported extension is rejected

- **WHEN** the input file extension is not one of `.md`, `.markdown`, `.txt`, `.html`, `.htm`
- **THEN** the system exits non-zero with a message listing supported formats

#### Scenario: Undecodable bytes are rejected

- **WHEN** the input file cannot be decoded as UTF-8 or a commonly used fallback encoding
- **THEN** the system exits non-zero with a message identifying the suspected encoding failure
