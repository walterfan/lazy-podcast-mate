## ADDED Requirements

### Requirement: Split script along semantic boundaries

The system SHALL split the rewritten script into ordered chunks that fit within the TTS provider's configured maximum length, splitting first on paragraph boundaries, then on sentence boundaries, and MUST NOT split in the middle of a sentence unless a single sentence exceeds the maximum length.

#### Scenario: Multi-paragraph script is chunked along paragraph boundaries

- **WHEN** the script contains three paragraphs each well under the chunk size limit
- **THEN** the chunker emits three chunks, one per paragraph, in original order

#### Scenario: Long paragraph is split at sentence boundaries

- **WHEN** a single paragraph exceeds the chunk size limit but contains multiple sentences
- **THEN** the chunker splits that paragraph at sentence terminators so every emitted chunk fits the limit and no sentence is split

#### Scenario: Oversized sentence triggers hard split

- **WHEN** a single sentence alone exceeds the chunk size limit
- **THEN** the chunker performs a hard character split as a last resort and logs a warning identifying the chunk index

### Requirement: Emit an ordered, indexed chunk manifest

The system SHALL persist the chunk list as an ordered manifest including `index`, `text`, `char_count`, and a stable content hash, so downstream TTS and checkpointing can reference chunks unambiguously.

#### Scenario: Chunk manifest is written to run directory

- **WHEN** the chunking stage completes
- **THEN** `chunks.json` in the run directory contains the ordered list of chunks with `index`, `text`, `char_count`, and `hash`

### Requirement: Produce chunks suitable for parallel synthesis

The system SHALL produce chunks that are independently synthesisable (no cross-chunk prosodic state required) so downstream TTS synthesis can run concurrently without audible discontinuities at chunk joins.

#### Scenario: Chunks can be synthesised independently

- **WHEN** the TTS stage synthesises chunks in any order
- **THEN** the concatenated audio (after post-production) plays without mid-sentence cuts
