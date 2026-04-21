## ADDED Requirements

### Requirement: Synthesise each chunk via a pluggable TTS provider

The system SHALL expose a `TTSSynthesizer` interface with a single `synthesize` method, and MUST support at least Volcano Engine, Azure TTS, and CosyVoice as interchangeable providers selected by configuration.

#### Scenario: Switching TTS provider via config only

- **WHEN** the user changes `TTS_PROVIDER` in configuration to another supported value
- **THEN** synthesis uses the new provider with no code changes outside configuration

### Requirement: Apply configured voice, speed, and volume

The system SHALL apply the configured voice identifier, speaking rate in the range 0.9–0.95, and a normalised volume to every chunk, and MUST document per-provider voice-ID mappings.

#### Scenario: Configured voice is used for synthesis

- **WHEN** the user configures a specific voice ID for the active TTS provider
- **THEN** every chunk is synthesised with that voice

#### Scenario: Rate is clamped to the valid range

- **WHEN** the user configures a rate outside the 0.9–0.95 range
- **THEN** the system rejects the configuration at start-up with a clear error

### Requirement: Retry transient failures and resume on rerun

The system SHALL retry transient TTS failures (network, rate-limit, 5xx) with exponential backoff up to a configured retry budget per chunk, and on rerun MUST reuse already-synthesised chunk files from the run cache instead of re-calling the provider.

#### Scenario: Transient failure is retried and succeeds

- **WHEN** a chunk synthesis fails with a 429 or 5xx and the retry budget is not exhausted
- **THEN** the system retries with exponential backoff and continues on success

#### Scenario: Rerun reuses cached chunk audio

- **WHEN** the pipeline is re-run for the same run with existing `chunk_<index>.*` files
- **THEN** no TTS call is made for those chunks and the files are used as-is for post-production

### Requirement: Surface permanent failures without aborting the run

The system SHALL, on permanent failure of a chunk (retry budget exhausted or 4xx other than rate-limit), record the failure in the run log with the chunk index and reason, and MUST either abort the run (strict mode, default) or continue with that chunk flagged (lenient mode) based on configuration.

#### Scenario: Permanent failure aborts in strict mode

- **WHEN** strict mode is configured and any chunk permanently fails
- **THEN** the run exits non-zero, the failure is recorded in `run.log`, and no post-production runs

#### Scenario: Permanent failure is flagged in lenient mode

- **WHEN** lenient mode is configured and a chunk permanently fails
- **THEN** the run records the failure, skips that chunk, and proceeds to post-production for the remaining chunks

### Requirement: Write chunk audio to the run cache

The system SHALL write each synthesised chunk to the run directory under `audio/chunk_<index>.<ext>` using a format supported by the post-production stage (MP3 or WAV as configured per provider).

#### Scenario: Chunk audio is written to the run directory

- **WHEN** a chunk is synthesised successfully
- **THEN** a file named `audio/chunk_<index>.<ext>` exists in the run directory and is readable by the post-production stage
