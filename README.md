# grch37-converter

Converts a list of rsid genotype calls (GRCh38) to their GRCh37 chromosome/position, using
the [Ensembl GRCh37 REST API](https://grch37.rest.ensembl.org/), and validates each genotype
against the GRCh37 alleles.

## Use case

Some raw DNA data providers (e.g. Atlas) report positions on the GRCh38 genome build,
but many downstream tools (e.g. GEDmatch) expect GRCh37. This script takes a GRCh38-based
rsid/genotype file and converts it to GRCh37 coordinates so it can be uploaded to those tools.

## Setup

```
pip install -r requirements.txt
```

For running the tests and linter/formatter:

```
pip install -r requirements-dev.txt
pytest
ruff format .   # auto-format
ruff check .    # lint
```

## Input

`data/input.txt` — tab-separated, with a header row. Must contain at least `rsid` and
`genotype` columns (any order, case-insensitive); other columns are ignored.

## Running

```
python main.py                    # full run: reads data/input.txt, writes the output files below
python main.py --dry-run          # report how many requests would be sent, no API calls
python main.py --single-batch     # send only the first batch, print the result, still write output
python main.py --max-workers 30   # tune how many batch requests run concurrently (default: 20)
python main.py --log-level DEBUG  # change log verbosity (default: INFO)
python clean.py                   # remove generated output files and cache directories
```

## Output

Each converted row is written to one of three tab-separated files, depending on the outcome —
the file it ends up in *is* the status, so there's no separate status column:

| file                 | meaning                                                              |
|----------------------|-----------------------------------------------------------------------|
| `data/output.txt`    | successfully converted rows                                           |
| `data/unmapped.txt`  | no GRCh37 mapping was returned for this rsid                          |
| `data/invalid.txt`   | a GRCh37 mapping was found, but the input genotype's bases don't match the GRCh37 alleles (after reverse-complementing them if the mapping is on the `-1` strand) |

`output.txt` and `unmapped.txt` share the same columns:

| column     | meaning                                                    |
|------------|--------------------------------------------------------------|
| rsid       | as given in the input                                        |
| chromosome | GRCh37 `seq_region_name`, empty in `unmapped.txt`             |
| position   | GRCh37 `start`, empty in `unmapped.txt`                       |
| genotype   | as given in the input                                         |

`invalid.txt` has those same four columns plus two more, to help diagnose why the genotype
didn't match:

| column         | meaning                                                                 |
|----------------|----------------------------------------------------------------------------|
| allele_string  | the GRCh37 mapping's raw `allele_string` (as returned by Ensembl, before any reverse-complementing) |
| var_class      | the variant's `var_class` (e.g. `SNP`, `indel`, `deletion`)                 |

## Project layout

- `main.py` — entry point: reads input, batches requests, converts rows, writes output.
- `clean.py` — removes generated output files (`data/*.txt` except `input.txt`) and cache directories (`__pycache__`, `.pytest_cache`, `.ruff_cache`).
- `cli.py` — CLI flag parsing.
- `file_io.py` — reading `data/input.txt` and writing the output files.
- `ensembl_api.py` — calls the Ensembl API, with retry/backoff on rate limiting.
- `convert.py` — GRCh38 → GRCh37 conversion and genotype validation logic.
- `logging_config.py` — logging setup.
- `tests/` — unit tests for `convert.py` and `file_io.py`, using mock data (no network calls).
