import json
import logging
import os
import time

from dotenv import load_dotenv

from cli import parse_args
from convert import convert_row
from ensembl_api import build_batches, fetch_variants
from file_io import ResultWriter, read_input_rows
from logging_config import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    args = parse_args()
    load_dotenv()
    configure_logging()

    api_url = os.environ["API_URL"]
    batch_size = int(os.environ["BATCH_SIZE"])
    request_delay_seconds = float(os.environ["REQUEST_DELAY_SECONDS"])

    # read_input_rows raises ValueError if the input file's header doesn't
    # have the columns we need; treat that as a user-facing config error
    # rather than a crash.
    try:
        input_rows = read_input_rows()
    except ValueError as error:
        raise SystemExit(str(error))
    logger.info("Read %d input row(s)", len(input_rows))

    batches = build_batches(input_rows, batch_size)

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

    with ResultWriter() as writer:
        for batch_number, batch in enumerate(batches, start=1):
            rsids = [row["rsid"] for row in batch]
            logger.info(
                "Fetching batch %d/%d (%d rsid(s))",
                batch_number,
                len(batches),
                len(rsids),
            )
            variant_data_by_rsid = fetch_variants(api_url, rsids)

            for row in batch:
                output_row = convert_row(row, variant_data_by_rsid.get(row["rsid"]))
                writer.write(output_row)
                if args.single_batch:
                    single_batch_rows.append(output_row)

            # Be polite to the API between requests; skip after the last
            # batch since there's nothing left to wait for.
            if batch_number < len(batches):
                time.sleep(request_delay_seconds)

        if args.single_batch:
            print(json.dumps(single_batch_rows, indent=2))

        logger.info(writer.summary())


if __name__ == "__main__":
    main()
