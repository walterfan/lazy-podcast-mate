## ADDED Requirements

### Requirement: Normalise whitespace and sentence boundaries

The system SHALL collapse runs of whitespace into single spaces, merge consecutive blank lines into a single paragraph break, and repair common sentence-boundary artefacts (e.g. missing space after a full stop, stray line breaks mid-sentence) so the text is suitable for TTS synthesis.

#### Scenario: Multiple blank lines are collapsed

- **WHEN** the cleaned `Article.body` contains three or more consecutive newlines between paragraphs
- **THEN** the cleaner reduces them to a single paragraph break

#### Scenario: Mid-sentence line break is repaired

- **WHEN** a sentence is split across two lines with no terminal punctuation on the first line
- **THEN** the cleaner joins the two lines with a single space

### Requirement: Apply user-defined term substitutions

The system SHALL apply a user-configurable term dictionary that maps written forms to spoken forms (e.g. `API -> 接口`, `K8s -> Kubernetes`) before emitting the cleaned text, preserving case sensitivity as configured per entry.

#### Scenario: Term dictionary substitution is applied

- **WHEN** the term dictionary maps `K8s` to `Kubernetes` and the article body contains `K8s cluster`
- **THEN** the cleaned text contains `Kubernetes cluster`

#### Scenario: Empty dictionary leaves text unchanged

- **WHEN** the term dictionary is empty
- **THEN** the cleaned text is identical to the whitespace-normalised input

### Requirement: Emit a deterministic cleaned text

The system SHALL produce byte-identical cleaned text on repeated runs of the same input and configuration, so downstream stages can checkpoint by content hash.

#### Scenario: Re-running cleaning is deterministic

- **WHEN** the same article and configuration are cleaned twice
- **THEN** the two cleaned outputs are byte-for-byte identical
