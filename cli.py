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
    return parser.parse_args()
