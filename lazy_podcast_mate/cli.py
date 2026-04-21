"""`lazy-podcast-mate` command-line entry point."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config.env import load_env
from .config.errors import ConfigError
from .config.loader import load_config
from .config.logging import setup_logging
from .ingestion.loader import load_article
from .orchestrator.checkpoints import RunPaths, Stage
from .orchestrator.runid import make_run_id
from .orchestrator.runner import RunOptions, run_pipeline
from .post.ffmpeg_check import ensure_ffmpeg_available

log = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lazy-podcast-mate",
        description="Turn an article into a publish-ready podcast MP3.",
    )
    parser.add_argument("--input", required=True, type=Path, help="Path to the article file.")
    parser.add_argument("--config", type=Path, default=None, help="Path to config.yaml (overrides LPM_CONFIG_PATH).")
    parser.add_argument("--run-id", type=str, default=None, help="Resume a specific run id.")
    parser.add_argument(
        "--force-stage",
        type=str,
        default=None,
        choices=[s.value for s in Stage],
        help="Re-run from this stage onwards.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--strict", dest="failure_mode", action="store_const", const="strict")
    group.add_argument("--lenient", dest="failure_mode", action="store_const", const="lenient")
    parser.add_argument(
        "--dry-run-script",
        action="store_true",
        help="Print the rewritten script and stop before TTS.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Increase stderr log verbosity to DEBUG."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        env = load_env()
        app_config, env = load_config(env=env, config_path=args.config)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    run_id = args.run_id
    run_dir = Path(app_config.output.run_data_directory).expanduser() / (run_id or "__tmp__")

    # If no run_id given, derive one from the article title (requires a quick
    # ingest peek — cheap, caches the article.json for the actual run later).
    if run_id is None:
        try:
            article = load_article(
                args.input, max_bytes=app_config.cleaning.max_input_bytes
            )
        except Exception as exc:
            print(f"Failed to read input: {exc}", file=sys.stderr)
            return 3
        run_id = make_run_id(article.title)
        run_dir = Path(app_config.output.run_data_directory).expanduser() / run_id

    paths = RunPaths(root=run_dir)
    paths.root.mkdir(parents=True, exist_ok=True)

    level = "DEBUG" if args.verbose else app_config.logging.level
    setup_logging(
        level=level,
        secrets=env.non_empty_secret_values,
        run_log_path=paths.run_log,
    )

    log.info("run_id=%s run_dir=%s", run_id, run_dir)

    try:
        ensure_ffmpeg_available()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 4

    force_stage = Stage(args.force_stage) if args.force_stage else None
    options = RunOptions(
        input_path=args.input,
        run_id=run_id,
        run_dir=run_dir,
        force_stage=force_stage,
        failure_mode_override=args.failure_mode,
        dry_run_script=args.dry_run_script,
    )

    outcome = run_pipeline(options, config=app_config, env=env)
    if outcome.status == "success":
        if outcome.output_path is not None:
            print(str(outcome.output_path))
        return 0

    print(
        f"Run {run_id} failed: {outcome.error}. See {paths.run_log} for details.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
