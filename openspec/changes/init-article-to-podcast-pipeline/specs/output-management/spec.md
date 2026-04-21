## ADDED Requirements

### Requirement: Write ID3 metadata to the final MP3

The system SHALL write ID3v2 tags to the exported MP3 including `title` (from the article), `artist` (from the configured creator name), `album` (from the configured show name), `date` (run date in ISO 8601), and `comment` (run ID and tool version).

#### Scenario: ID3 tags are written on export

- **WHEN** the export stage completes successfully
- **THEN** the resulting MP3 has ID3v2 tags for `title`, `artist`, `album`, `date`, and `comment` populated as configured

### Requirement: Place output in a configured location with a deterministic filename

The system SHALL write the final MP3 to the configured output directory using a deterministic filename pattern that incorporates the article title slug and run date (default `{date}-{slug}.mp3`), and MUST NOT silently overwrite an existing file.

#### Scenario: Deterministic filename is used

- **WHEN** the default filename pattern is in effect and the article title is "Hello World" on 2026-04-18
- **THEN** the output file is named `2026-04-18-hello-world.mp3` in the configured output directory

#### Scenario: Existing file is not silently overwritten

- **WHEN** a file with the computed output path already exists
- **THEN** the system either appends a numeric suffix or exits non-zero based on the configured `on_existing` policy, but never silently overwrites

### Requirement: Append a structured entry to the run history

The system SHALL append one structured JSON line to `data/history.jsonl` per run, containing `run_id`, `source_path`, `output_path`, `status`, `started_at`, `finished_at`, `duration_seconds`, `llm_provider`, `tts_provider`, and any error summary.

#### Scenario: Run history is appended on success

- **WHEN** a run completes successfully
- **THEN** `data/history.jsonl` has one new line whose `status` field equals `success` and whose `output_path` points at the exported MP3

#### Scenario: Run history is appended on failure

- **WHEN** a run fails at any stage
- **THEN** `data/history.jsonl` has one new line whose `status` field equals `failed` and whose error summary names the failing stage
