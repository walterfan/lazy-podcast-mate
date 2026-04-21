## ADDED Requirements

### Requirement: Concatenate synthesised chunks in order

The system SHALL concatenate chunk audio files in the order given by the chunk manifest, producing a single continuous voice track with no audible gaps beyond the configured inter-chunk silence.

#### Scenario: Chunks are joined in manifest order

- **WHEN** post-production runs over a manifest of N chunks
- **THEN** the resulting voice track contains all N chunks in order and its duration equals the sum of chunk durations plus the configured inter-chunk silence times (N-1)

### Requirement: Apply fade in and fade out

The system SHALL apply a fade-in at the start and a fade-out at the end of the concatenated voice track using the configured durations (default 500 ms each), and MUST apply them after BGM mixing when BGM is present.

#### Scenario: Default fades are applied

- **WHEN** no custom fade duration is configured
- **THEN** the final audio has a 500 ms fade-in at the start and a 500 ms fade-out at the end

### Requirement: Mix background music below the voice

The system SHALL, when a BGM file is configured, mix it underneath the voice track at 10–15% of the voice level, looping or trimming as needed to match the voice duration, and MUST NOT let BGM level rise above the voice level at any point.

#### Scenario: BGM is mixed below voice at configured level

- **WHEN** the user configures a BGM file and a BGM-to-voice ratio within 10–15%
- **THEN** the final audio contains both tracks and the BGM RMS level is within the configured ratio of the voice RMS level

#### Scenario: No BGM configured produces voice-only output

- **WHEN** no BGM file is configured
- **THEN** the final audio contains only the voice track with fades applied

### Requirement: Apply noise reduction and loudness normalisation

The system SHALL apply a light noise-reduction pass on the voice track, followed by loudness normalisation targeting −16 LUFS integrated with a −1 dBTP true-peak ceiling, before mixing BGM.

#### Scenario: Loudness is normalised to the podcast target

- **WHEN** post-production completes for any run
- **THEN** the final audio's integrated loudness is within ±1 LU of −16 LUFS and the true peak does not exceed −1 dBTP

### Requirement: Export 320 kbps MP3

The system SHALL export the final audio as an MP3 file encoded at 320 kbps CBR, 44.1 kHz or 48 kHz stereo, and MUST reject export if the encoder falls back to a different bitrate.

#### Scenario: Final MP3 is 320 kbps

- **WHEN** the export stage completes
- **THEN** the output file is an MP3 with a 320 kbps CBR bitrate at 44.1 kHz or 48 kHz stereo

### Requirement: Fail fast when ffmpeg is missing

The system SHALL verify at start-up that `ffmpeg` is available on `PATH` and MUST exit non-zero with install instructions before any network calls are made when it is missing.

#### Scenario: Missing ffmpeg is detected early

- **WHEN** `ffmpeg` is not available on `PATH` at start-up
- **THEN** the pipeline exits non-zero with a message naming `ffmpeg` and pointing to install instructions, and no LLM or TTS calls are made
