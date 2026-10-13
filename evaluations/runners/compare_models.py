"""CLI for replayable local-model RAG comparisons."""

from __future__ import annotations

import argparse
import sys

from cpea.bootstrap import AssistantRuntime
from cpea.application.errors import DependencyUnavailable
from evaluations.metadata import default_output
from evaluations.runners.model_comparison import compare_models, load_cases, write_records


def main(argv=None, *, runtime=None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare local models on frozen RAG context"
    )
    parser.add_argument("--dataset", required=True, help="UTF-8 JSONL evaluation cases")
    parser.add_argument("--output", help="New private result path; defaults to artifacts/evaluations/<run-id>/")
    parser.add_argument("--env-file")
    parser.add_argument(
        "--models",
        nargs="+",
        required=True,
        help="Two or more provider model names, for example a 4B and an 8B model",
    )
    parser.add_argument(
        "--preparation-model",
        help=(
            "Model used once for SQL/context preparation; defaults to the first "
            "entry in --models"
        ),
    )
    parser.add_argument(
        "--no-warmup",
        action="store_true",
        help="Measure cold model loading as part of TTFT instead of warming each model",
    )
    args = parser.parse_args(argv)
    runtime = runtime if runtime is not None else AssistantRuntime.from_env(args.env_file)
    try:
        runtime.require_execution()
    except DependencyUnavailable as exc:
        print(f'{exc.code}: {exc}', file=sys.stderr)
        return 3
    records = compare_models(
        load_cases(args.dataset),
        args.models,
        preparation_model=args.preparation_model,
        warmup=not args.no_warmup,
        runtime=runtime,
    )
    if not records:
        raise ValueError("dataset is empty")
    output = args.output or default_output(records[0].run_metadata, "model-comparison")
    write_records(output, records)
    print(f"wrote {len(records)} evaluation records to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
