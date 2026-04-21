## ADDED Requirements

### Requirement: Rewrite cleaned text into a spoken podcast script

The system SHALL call a configured LLM provider with a fixed, versioned system prompt and the cleaned article text, and MUST return a rewritten script that has an opening, body with transitions, and a closing, and that preserves the author's core viewpoints without adding fabricated facts.

#### Scenario: Script includes opening, transitions, and closing

- **WHEN** the LLM stage runs on a valid cleaned article
- **THEN** the emitted script contains at least one opening paragraph, at least one transition cue between major sections, and a closing summary paragraph

#### Scenario: Core viewpoints are preserved

- **WHEN** the cleaned article states a specific technical claim (e.g. a version number or benchmark result)
- **THEN** the same claim appears in the rewritten script without being altered or omitted

### Requirement: Enforce narrator persona

The system SHALL ensure the rewritten script uses a calm, seasoned, professional tone without exaggerated emotional language, rhetorical exclamations, or emojis, matching the configured persona.

#### Scenario: Persona tone is enforced

- **WHEN** the LLM stage produces a script
- **THEN** the script contains no emojis and no consecutive exclamation marks, and the persona is logged alongside the prompt version

### Requirement: Pluggable LLM provider behind a standard interface

The system SHALL expose a `ScriptRewriter` interface with a single `rewrite` method, and MUST allow at least one of OpenAI-compatible, Anthropic, and a domestic commercial LLM provider to be selected by configuration without changes to orchestration, cleaning, or downstream stages.

#### Scenario: Switching provider via config only

- **WHEN** the user changes `LLM_PROVIDER` in configuration from one supported value to another and re-runs the pipeline
- **THEN** the new provider is used and no code changes outside configuration are required

### Requirement: Fail fast when script rewriting cannot succeed

The system SHALL fail the run with a clear error, without advancing to TTS, when the LLM provider is unreachable after configured retries, when the provider returns an empty response, or when the cleaned input exceeds the configured token budget.

#### Scenario: LLM exceeds retry budget

- **WHEN** every configured retry of the LLM call fails with a network or rate-limit error
- **THEN** the run exits non-zero with the underlying provider error logged and no TTS calls are made

#### Scenario: Input exceeds token budget

- **WHEN** the cleaned article's estimated token count exceeds the configured budget
- **THEN** the run exits non-zero with a message naming the budget and suggested remediation

### Requirement: Record the prompt version and provider in the run log

The system SHALL write the prompt version identifier, provider name, and model identifier into the run log alongside the produced script, so runs are reproducible and drift is diffable.

#### Scenario: Run log captures prompt metadata

- **WHEN** the script stage completes successfully
- **THEN** `run.log` contains a structured entry with `prompt_version`, `provider`, and `model` fields
