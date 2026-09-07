import json
import logging
from concurrent.futures import ThreadPoolExecutor

from cli import parse_args
from convert import convert_row
from ensembl_api import API_URL, BATCH_SIZE, build_batches, fetch_variants
from file_io import ResultWriter, read_input_rows
from logging_config import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)

    # read_input_rows raises ValueError if the input file's header doesn't
    # have the columns we need; treat that as a user-facing config error
    # rather than a crash.
    try:
        input_rows = read_input_rows()
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
        results = executor.map(
            lambda batch: fetch_variants(API_URL, [row["rsid"] for row in batch]),
            batches,
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


if __name__ == "__main__":
    main()
