#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from unstructured_client._hooks.custom.split_pdf_hook import (
    MAX_CONCURRENCY_LEVEL,
    get_optimal_split_size,
)

from unstructured.documents.elements import Element
from unstructured.partition.api import partition_multiple_via_api, partition_via_api


def _load_request_kwargs(inline_json: str | None, json_file: str | None) -> dict[str, Any]:
    if inline_json and json_file:
        raise ValueError("Only one of --request-kwargs-json and --request-kwargs-file can be set.")

    raw_value = None
    if json_file:
        raw_value = Path(json_file).expanduser().read_text()
    elif inline_json:
        raw_value = inline_json

    if raw_value is None:
        return {}

    request_kwargs = json.loads(raw_value)
    if not isinstance(request_kwargs, dict):
        raise ValueError("Request kwargs JSON must decode to an object.")
    return request_kwargs


def _summarize_elements(elements: list[Element]) -> str:
    type_counts = Counter(type(element).__name__ for element in elements)
    counts_str = ", ".join(f"{name}={count}" for name, count in sorted(type_counts.items()))
    return f"{len(elements)} elements [{counts_str}]"


def _get_pdf_page_count(file_path: str, request_kwargs: dict[str, Any]) -> int:
    page_range = request_kwargs.get("split_pdf_page_range")
    if page_range is not None:
        if (
            not isinstance(page_range, list)
            or len(page_range) != 2
            or not all(isinstance(page_number, int) for page_number in page_range)
        ):
            raise ValueError(
                "split_pdf_page_range must be a two-item integer list when used with "
                "--page-batch-size.",
            )
        start_page, end_page = page_range
        if start_page < 1 or end_page < start_page:
            raise ValueError(
                "split_pdf_page_range must contain positive page numbers in ascending order.",
            )
        return end_page - start_page + 1

    with open(file_path, "rb") as pdf_file:
        return len(PdfReader(pdf_file).pages)


def _resolve_split_pdf_concurrency_level(
    files: list[str],
    request_kwargs: dict[str, Any],
    page_batch_size: int | None,
    split_pdf_page: bool | None,
) -> None:
    if split_pdf_page is not None:
        request_kwargs["split_pdf_page"] = split_pdf_page

    if page_batch_size is None:
        return

    if page_batch_size < 2:
        raise ValueError("--page-batch-size must be at least 2.")
    if len(files) != 1:
        raise ValueError(
            "--page-batch-size currently supports exactly one input PDF. "
            "Use --request-kwargs-json for custom multi-file split settings.",
        )
    if request_kwargs.get("split_pdf_concurrency_level") is not None:
        raise ValueError(
            "Do not combine --page-batch-size with split_pdf_concurrency_level in "
            "--request-kwargs-json/--request-kwargs-file.",
        )
    if request_kwargs.get("split_pdf_page") is False:
        raise ValueError("--page-batch-size requires split_pdf_page to be enabled.")

    file_path = Path(files[0])
    if file_path.suffix.lower() != ".pdf":
        raise ValueError("--page-batch-size is only supported for PDF inputs.")

    page_count = _get_pdf_page_count(files[0], request_kwargs)
    achievable_batch_sizes: dict[int, int] = {}
    for concurrency_level in range(1, MAX_CONCURRENCY_LEVEL + 1):
        split_size = get_optimal_split_size(page_count, concurrency_level)
        achievable_batch_sizes.setdefault(split_size, concurrency_level)

    if page_batch_size not in achievable_batch_sizes:
        achievable_values = ", ".join(str(value) for value in sorted(achievable_batch_sizes))
        raise ValueError(
            f"--page-batch-size {page_batch_size} is not achievable for {page_count} PDF page(s). "
            f"Achievable batch sizes: {achievable_values}.",
        )

    request_kwargs["split_pdf_page"] = True
    request_kwargs["split_pdf_concurrency_level"] = achievable_batch_sizes[page_batch_size]


def _run_request(
    files: list[str],
    api_url: str | None,
    api_key: str | None,
    request_kwargs: dict[str, Any],
) -> list[list[Element]]:
    if len(files) == 1:
        return [
            partition_via_api(
                filename=files[0],
                api_url=api_url,
                api_key=api_key,
                **request_kwargs,
            )
        ]

    return partition_multiple_via_api(
        filenames=files,
        api_url=api_url,
        api_key=api_key,
        **request_kwargs,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one or more partition_via_api requests for local e2e and profiling work.",
    )
    parser.add_argument("files", nargs="+", help="One or more input files to send to the API.")
    parser.add_argument(
        "--strategy",
        "--partition-mode",
        dest="strategy",
        default="auto",
        help=(
            "Partition strategy/mode to send unless request kwargs already define one, "
            'for example "fast", "hi_res", or "ocr_only".'
        ),
    )
    parser.add_argument("--api-url", help="Explicit API URL override.")
    parser.add_argument("--api-key", help="Explicit API key override.")
    parser.add_argument(
        "--split-pdf-page",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Enable or disable client-side split-PDF partitioning before upload. "
            "Useful for comparing split vs non-split memory behavior."
        ),
    )
    parser.add_argument(
        "--page-batch-size",
        type=int,
        help=(
            "Target pages per split-PDF request for a single PDF input. "
            "This is translated into the client SDK's split_pdf_concurrency_level."
        ),
    )
    parser.add_argument(
        "--request-kwargs-json",
        help="Inline JSON object of extra request kwargs, e.g. '{\"coordinates\": \"true\"}'.",
    )
    parser.add_argument(
        "--request-kwargs-file",
        help="Path to a JSON file containing extra request kwargs.",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=0,
        help="Number of warmup requests to run before measured iterations.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Number of measured requests to run.",
    )
    parser.add_argument(
        "--pause-between",
        type=float,
        default=0.0,
        help="Seconds to sleep between measured requests.",
    )
    args = parser.parse_args()

    files = [str(Path(file).expanduser().resolve()) for file in args.files]
    request_kwargs = _load_request_kwargs(args.request_kwargs_json, args.request_kwargs_file)
    _resolve_split_pdf_concurrency_level(
        files=files,
        request_kwargs=request_kwargs,
        page_batch_size=args.page_batch_size,
        split_pdf_page=args.split_pdf_page,
    )
    request_kwargs.setdefault("strategy", args.strategy)

    if args.repeat < 1:
        raise ValueError("--repeat must be at least 1.")
    if args.warmup < 0:
        raise ValueError("--warmup must be at least 0.")
    if args.pause_between < 0:
        raise ValueError("--pause-between must be at least 0.")

    measured_durations: list[float] = []
    total_runs = args.warmup + args.repeat

    for run_idx in range(total_runs):
        is_warmup = run_idx < args.warmup
        phase = "warmup" if is_warmup else "measured"
        phase_idx = run_idx + 1 if is_warmup else run_idx - args.warmup + 1

        start = time.perf_counter()
        documents = _run_request(files, args.api_url, args.api_key, request_kwargs)
        duration = time.perf_counter() - start

        if any(len(document) == 0 for document in documents):
            raise ValueError("The API returned an empty document for at least one input file.")

        if not is_warmup:
            measured_durations.append(duration)

        doc_summaries = "; ".join(
            f"{Path(file).name}: {_summarize_elements(document)}"
            for file, document in zip(files, documents)
        )
        print(f"{phase} request {phase_idx}: {duration:.2f}s | {doc_summaries}")

        if args.pause_between and not is_warmup and run_idx != total_runs - 1:
            time.sleep(args.pause_between)

    avg_duration = sum(measured_durations) / len(measured_durations)
    print(f"measured requests: {args.repeat}, average duration: {avg_duration:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
