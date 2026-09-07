import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch GRCh37 variant data for rsids from input.txt."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="only report how many requests would be sent, without calling the API",
    )
    parser.add_argument(
        "--single-batch",
        action="store_true",
        help="send only the first batch and print the result",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=20,
        help="number of batch requests to run concurrently (default: 20)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level, e.g. INFO, DEBUG (default: INFO)",
    )
    return parser.parse_args()
