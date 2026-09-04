from ensembl_api import build_batches


def test_build_batches_splits_rows_into_fixed_size_chunks():
    rows = [{"rsid": f"rs{i}"} for i in range(5)]

    batches = build_batches(rows, batch_size=2)

    assert batches == [
        [{"rsid": "rs0"}, {"rsid": "rs1"}],
        [{"rsid": "rs2"}, {"rsid": "rs3"}],
        [{"rsid": "rs4"}],
    ]


def test_build_batches_empty_input():
    assert build_batches([], batch_size=200) == []
