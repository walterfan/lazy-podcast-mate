## ADDED Requirements

### Requirement: Load secrets from environment variables only

The system SHALL load API keys, endpoints, and other secrets exclusively from environment variables (optionally populated via a `.env` file loaded by `python-dotenv`), and MUST NOT accept secrets from the `config.yaml` file or the command line.

#### Scenario: Secrets come from environment

- **WHEN** `LLM_API_KEY` is set in `.env` and the pipeline runs
- **THEN** the LLM provider uses that value and `config.yaml` contains no API key field

#### Scenario: Secret in config.yaml is rejected

- **WHEN** the loaded `config.yaml` contains a key whose name matches a known secret pattern (e.g. `api_key`, `token`, `secret`)
- **THEN** the system exits non-zero at start-up with a message explaining that secrets belong in environment variables

### Requirement: Load behavioural configuration from a YAML file

The system SHALL load behavioural parameters — cleaning rules, term dictionary, TTS voice/rate/volume/concurrency, chunk size, BGM file path and level, fade durations, retry budgets, output directory, filename pattern, log level — from a single YAML file whose path defaults to `config.yaml` in the project root and can be overridden by `LPM_CONFIG_PATH`.

#### Scenario: Default config.yaml is loaded

- **WHEN** `LPM_CONFIG_PATH` is not set and a `config.yaml` exists in the project root
- **THEN** the system loads behavioural parameters from that file at start-up

#### Scenario: LPM_CONFIG_PATH overrides the default

- **WHEN** `LPM_CONFIG_PATH` is set to an absolute path
- **THEN** the system loads the file at that path instead of `config.yaml`

### Requirement: Validate required configuration at start-up

The system SHALL validate the merged configuration (env + YAML) at start-up against a typed schema, and MUST exit non-zero with a clear message listing every missing or invalid key before any stage runs.

#### Scenario: Missing required key fails fast

- **WHEN** a required key (e.g. `TTS_PROVIDER`, `LLM_API_KEY`, or the output directory) is missing or unset
- **THEN** the system exits non-zero before ingestion with a message naming the missing key

### Requirement: Redact secrets from logs

The system SHALL install a logging filter that masks any value matching a configured secret (or any value originating from an env var on the secret allowlist) wherever it appears in log output.

#### Scenario: API key is redacted in logs

- **WHEN** a provider call is logged and the log contains the literal API key value
- **THEN** the emitted log line shows the value masked (e.g. `***`) and never the raw key
