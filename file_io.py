import logging
import os
from pathlib import Path

from convert import InputRow, OutputRow, Status

logger = logging.getLogger(__name__)

INPUT_PATH = Path("data/input.txt")
# A small, committed file of public reference SNPs, so the tool can be run
# straight after cloning without supplying real DNA data.
SAMPLE_INPUT_PATH = Path("data/input.sample.txt")
OUTPUT_PATH = Path("data/output.txt")
UNMAPPED_PATH = Path("data/unmapped.txt")
INVALID_PATH = Path("data/invalid.txt")

REQUIRED_COLUMNS = ("rsid", "genotype")
COMMON_OUTPUT_COLUMNS = ("rsid", "chromosome", "position", "genotype")
OUTPUT_COLUMNS_BY_STATUS = {
    Status.OK: COMMON_OUTPUT_COLUMNS,
    Status.UNMAPPED: COMMON_OUTPUT_COLUMNS,
    Status.INVALID: COMMON_OUTPUT_COLUMNS + ("allele_string", "var_class"),
}
DEFAULT_OUTPUT_PATHS_BY_STATUS = {
    Status.OK: OUTPUT_PATH,
    Status.UNMAPPED: UNMAPPED_PATH,
    Status.INVALID: INVALID_PATH,
}


def _find_column_indices(header: list[str], columns: tuple[str, ...]) -> dict[str, int]:
    indices = {}
    for column in columns:
        if column not in header:
            raise ValueError(f"Could not find a {column!r} column in header: {header}")
        indices[column] = header.index(column)
    return indices


def read_input_rows(input_path: Path = INPUT_PATH) -> list[InputRow]:
    with input_path.open("r", encoding="utf-8") as input_file:
        header = [
            column.strip().lower()
            for column in input_file.readline().rstrip("\n").split("\t")
        ]
        indices = _find_column_indices(header, REQUIRED_COLUMNS)

        return [
            {
                column: line.rstrip("\n").split("\t")[index]
                for column, index in indices.items()
            }
            for line in input_file
        ]


STATUS_LABELS = {
    Status.OK: "converted to GRCh37",
    Status.UNMAPPED: "unmapped",
    Status.INVALID: "invalid",
}


class ResultWriter:
    """Streams conversion results straight to disk, split by status, instead
    of holding the whole result set in memory for one write at the end.

    Writes go to temp files alongside the real output paths; the real paths
    are only created (via atomic rename) if the whole run finishes without
    error, so a run that crashes partway through never leaves a partial
    output file that looks like a complete one."""

    def __init__(
        self, paths_by_status: dict[Status, Path] = DEFAULT_OUTPUT_PATHS_BY_STATUS
    ):
        self.paths = paths_by_status
        self._temp_paths = {
            status: path.with_name(path.name + ".tmp")
            for status, path in paths_by_status.items()
        }
        self._files = {
            status: temp_path.open("w", encoding="utf-8")
            for status, temp_path in self._temp_paths.items()
        }
        self.counts: dict[Status, int] = {status: 0 for status in paths_by_status}
        for status, file in self._files.items():
            file.write("\t".join(OUTPUT_COLUMNS_BY_STATUS[status]) + "\n")

    def write(self, row: OutputRow) -> None:
        status = row["status"]
        columns = OUTPUT_COLUMNS_BY_STATUS[status]
        self._files[status].write(
            "\t".join(str(row[column]) for column in columns) + "\n"
        )
        self.counts[status] += 1

    def summary(self) -> str:
        total = sum(self.counts.values())
        breakdown = ", ".join(
            f"{self.counts[status]} {STATUS_LABELS[status]} ({self.paths[status]})"
            for status in self.paths
        )
        return f"Processed {total} row(s): {breakdown}."

    def close(self) -> None:
        for file in self._files.values():
            file.close()

    def _commit(self) -> None:
        # Same directory as the real path, so this is an atomic rename
        # rather than a cross-filesystem copy.
        for status, temp_path in self._temp_paths.items():
            os.replace(temp_path, self.paths[status])

    def _discard(self) -> None:
        for temp_path in self._temp_paths.values():
            temp_path.unlink(missing_ok=True)
        logger.error(
            "Run failed before completion; no output files were written "
            "(partial results discarded)."
        )

    def __enter__(self) -> "ResultWriter":
        return self

    def __exit__(self, exc_type, *exc_info) -> None:
        self.close()
        if exc_type is None:
            self._commit()
        else:
            self._discard()
