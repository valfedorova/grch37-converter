import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from cli import parse_args
from convert import convert_row
from ensembl_api import (
    API_URL,
    BATCH_SIZE,
    build_batches,
    fetch_variants,
    get_rate_limit_info,
)
from file_io import INPUT_PATH, SAMPLE_INPUT_PATH, ResultWriter, read_input_rows
from logging_config import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)

    # Both of these are user-facing setup mistakes (no input file, or a file
    # whose header lacks the columns we need) rather than bugs, so report them
    # as a message and a non-zero exit instead of a traceback.
    try:
        input_rows = read_input_rows()
    except FileNotFoundError:
        raise SystemExit(
            f"No input file at {INPUT_PATH}.\n"
            f"To try the tool on the bundled sample of public reference SNPs:\n"
            f"    cp {SAMPLE_INPUT_PATH} {INPUT_PATH}"
        )
    except ValueError as error:
        raise SystemExit(str(error))
    logger.info("Read %d input row(s)", len(input_rows))

    batches = build_batches(input_rows, BATCH_SIZE)

    if args.dry_run:
        request_count = len(batches)
        rsid_count = len(input_rows)
        print(
            f"Dry run: would send {request_count} request(s) for {rsid_count} rsid(s)."
        )
        return

    if args.single_batch:
        batches = batches[:1]

    start_time = time.monotonic()

    # Only populated in --single-batch mode, to print what was converted.
    # ResultWriter streams everything else straight to disk, so we don't
    # normally hold converted rows in memory.
    single_batch_rows = []

    with (
        ResultWriter() as writer,
        ThreadPoolExecutor(max_workers=args.max_workers) as executor,
    ):
        # executor.map keeps results in submission order even though the
        # underlying requests run concurrently, so batches are still
        # written in input order.
        last_batch_index = len(batches) - 1
        results = executor.map(
            lambda indexed_batch: fetch_variants(
                API_URL,
                [row["rsid"] for row in indexed_batch[1]],
                capture_headers=indexed_batch[0] == last_batch_index,
            ),
            enumerate(batches),
        )

        for batch_number, (batch, variant_data_by_rsid) in enumerate(
            zip(batches, results), start=1
        ):
            logger.info(
                "Processing batch %d/%d (%d rsid(s))",
                batch_number,
                len(batches),
                len(batch),
            )

            for row in batch:
                output_row = convert_row(row, variant_data_by_rsid.get(row["rsid"]))
                writer.write(output_row)
                if args.single_batch:
                    single_batch_rows.append(output_row)

        if args.single_batch:
            print(json.dumps(single_batch_rows, indent=2))

        logger.info(writer.summary())

        elapsed = timedelta(seconds=round(time.monotonic() - start_time))
        logger.info("Run finished in %s (H:MM:SS).", elapsed)

        rate_limit_info = get_rate_limit_info()
        if rate_limit_info:
            details = ", ".join(f"{k}={v}" for k, v in rate_limit_info.items())
            logger.info("Rate limit status (last response): %s", details)


if __name__ == "__main__":
    main()
