import pytest

from convert import Status
from file_io import ResultWriter, read_input_rows


def test_read_input_rows_finds_columns_by_name_in_any_order(tmp_path):
    input_path = tmp_path / "input.txt"
    input_path.write_text(
        "chromosome\tgenotype\tposition\trsid\n"
        "1\tCC\t630053\trs9701055\n"
        "1\tTT\t632828\trs9701872\n",
        encoding="utf-8",
    )

    rows = read_input_rows(input_path)

    assert rows == [
        {"genotype": "CC", "rsid": "rs9701055"},
        {"genotype": "TT", "rsid": "rs9701872"},
    ]


def test_read_input_rows_skips_blank_lines(tmp_path):
    input_path = tmp_path / "input.txt"
    input_path.write_text(
        "rsid\tgenotype\nrs9701055\tCC\n\n   \nrs9701872\tTT\n\n",
        encoding="utf-8",
    )

    rows = read_input_rows(input_path)

    assert rows == [
        {"rsid": "rs9701055", "genotype": "CC"},
        {"rsid": "rs9701872", "genotype": "TT"},
    ]


def test_read_input_rows_raises_when_rsid_column_missing(tmp_path):
    input_path = tmp_path / "input.txt"
    input_path.write_text(
        "chromosome\tgenotype\tposition\n1\tCC\t630053\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="rsid"):
        read_input_rows(input_path)


def test_result_writer_splits_rows_by_status_with_different_columns(tmp_path):
    output_path = tmp_path / "output.txt"
    unmapped_path = tmp_path / "unmapped.txt"
    invalid_path = tmp_path / "invalid.txt"

    with ResultWriter(
        {
            Status.OK: output_path,
            Status.UNMAPPED: unmapped_path,
            Status.INVALID: invalid_path,
        }
    ) as writer:
        writer.write(
            {
                "rsid": "rs1",
                "chromosome": "1",
                "position": 100,
                "genotype": "CC",
                "status": Status.OK,
            }
        )
        writer.write(
            {
                "rsid": "rs2",
                "chromosome": "",
                "position": "",
                "genotype": "TT",
                "status": Status.UNMAPPED,
            }
        )
        writer.write(
            {
                "rsid": "rs3",
                "chromosome": "1",
                "position": 200,
                "genotype": "II",
                "status": Status.INVALID,
                "allele_string": "T/-",
                "var_class": "deletion",
            }
        )

    assert writer.counts == {Status.OK: 1, Status.UNMAPPED: 1, Status.INVALID: 1}

    assert output_path.read_text(encoding="utf-8") == (
        "rsid\tchromosome\tposition\tgenotype\nrs1\t1\t100\tCC\n"
    )
    assert unmapped_path.read_text(encoding="utf-8") == (
        "rsid\tchromosome\tposition\tgenotype\nrs2\t\t\tTT\n"
    )
    assert invalid_path.read_text(encoding="utf-8") == (
        "rsid\tchromosome\tposition\tgenotype\tallele_string\tvar_class\n"
        "rs3\t1\t200\tII\tT/-\tdeletion\n"
    )


def test_result_writer_discards_partial_output_when_run_fails(tmp_path):
    output_path = tmp_path / "output.txt"
    unmapped_path = tmp_path / "unmapped.txt"
    invalid_path = tmp_path / "invalid.txt"

    with pytest.raises(RuntimeError):
        with ResultWriter(
            {
                Status.OK: output_path,
                Status.UNMAPPED: unmapped_path,
                Status.INVALID: invalid_path,
            }
        ) as writer:
            writer.write(
                {
                    "rsid": "rs1",
                    "chromosome": "1",
                    "position": 100,
                    "genotype": "CC",
                    "status": Status.OK,
                }
            )
            raise RuntimeError("simulated batch failure")

    assert not output_path.exists()
    assert not unmapped_path.exists()
    assert not invalid_path.exists()
    assert list(tmp_path.iterdir()) == []


def test_result_writer_summary_reports_counts_and_paths(tmp_path):
    output_path = tmp_path / "output.txt"
    unmapped_path = tmp_path / "unmapped.txt"
    invalid_path = tmp_path / "invalid.txt"

    with ResultWriter(
        {
            Status.OK: output_path,
            Status.UNMAPPED: unmapped_path,
            Status.INVALID: invalid_path,
        }
    ) as writer:
        writer.write(
            {
                "rsid": "rs1",
                "chromosome": "1",
                "position": 100,
                "genotype": "CC",
                "status": Status.OK,
            }
        )

        summary = writer.summary()

    assert summary == (
        f"Processed 1 row(s): 1 converted to GRCh37 ({output_path}), "
        f"0 unmapped ({unmapped_path}), 0 invalid ({invalid_path})."
    )
