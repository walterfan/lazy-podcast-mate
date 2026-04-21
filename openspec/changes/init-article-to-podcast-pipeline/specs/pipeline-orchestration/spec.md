## ADDED Requirements

### Requirement: Run all stages end-to-end from a single command

The system SHALL provide a single CLI entry point that, given an article path, executes ingestion → cleaning → script rewriting → chunking → TTS synthesis → post-production → output in order, without requiring any manual step between stages.

#### Scenario: End-to-end run from CLI

- **WHEN** the user runs the CLI entry point with a valid article path and valid configuration
- **THEN** the pipeline executes every stage in order and writes a final MP3 to the configured output directory

### Requirement: Assign a unique run ID and isolate run artefacts

The system SHALL assign each run a unique `run_id` (timestamp + article slug) and MUST place every intermediate artefact for that run under `data/runs/<run_id>/`.

#### Scenario: Per-run directory is created

- **WHEN** a new run starts
- **THEN** a directory `data/runs/<run_id>/` exists and receives `article.json`, `script.md`, `chunks.json`, `audio/`, `run.log`, and the final MP3 (or a copy of its path)

### Requirement: Checkpoint each stage and skip completed stages on rerun

The system SHALL check for the expected output artefacts of each stage and MUST skip the stage when its artefacts already exist and validate, so a re-run of the same `run_id` only repeats failed or missing stages.

#### Scenario: Completed stages are skipped on rerun

- **WHEN** the pipeline is re-run for an existing `run_id` whose `script.md` and a subset of `audio/chunk_*.*` files already exist
- **THEN** the cleaning and script stages are skipped, only missing chunks are synthesised, and post-production runs on the full set

### Requirement: Force re-run of a specific stage

The system SHALL accept a `--force-stage <name>` flag on the CLI that invalidates the checkpoint for the named stage and every downstream stage, forcing them to re-run.

#### Scenario: Forcing re-run of the script stage

- **WHEN** the user passes `--force-stage script` for an existing `run_id`
- **THEN** the pipeline re-runs script rewriting, chunking, TTS, post-production, and output, and does not re-run ingestion or cleaning

### Requirement: Emit a structured per-run log

The system SHALL write structured JSON-lines entries to `data/runs/<run_id>/run.log` for every stage start, stage end, provider call, retry, and error, including timestamps and stage identifiers.

#### Scenario: Log captures each stage

- **WHEN** the pipeline completes any run (success or failure)
- **THEN** `run.log` contains at least one entry per executed stage with stage name, start time, end time, and outcome

### Requirement: Surface progress and errors to the user

The system SHALL print human-readable progress to stderr as stages start and complete, and on failure MUST print the failing stage, the error cause, and the path to `run.log` for further inspection.

#### Scenario: Failure points the user at the run log

- **WHEN** any stage fails
- **THEN** stderr includes the failing stage name and the absolute path to `run.log`
