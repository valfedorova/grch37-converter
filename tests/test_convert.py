from convert import (
    Status,
    convert_row,
    find_grch37_mapping,
    is_genotype_valid,
    reverse_complement,
)


def make_variant_data(mappings, var_class="SNP"):
    return {"mappings": mappings, "var_class": var_class}


def make_mapping(strand=1, allele_string="C/T", start=565433, seq_region_name="1"):
    return {
        "assembly_name": "GRCh37",
        "seq_region_name": seq_region_name,
        "start": start,
        "strand": strand,
        "allele_string": allele_string,
    }


def test_reverse_complement_pairs():
    assert reverse_complement("AG") == "CT"
    assert reverse_complement("TT") == "AA"
    assert reverse_complement("ACGT") == "ACGT"


def test_find_grch37_mapping_picks_matching_assembly():
    grch38_mapping = {"assembly_name": "GRCh38"}
    grch37_mapping = {"assembly_name": "GRCh37"}
    assert find_grch37_mapping([grch38_mapping, grch37_mapping]) is grch37_mapping


def test_find_grch37_mapping_returns_none_when_absent():
    assert find_grch37_mapping([{"assembly_name": "GRCh38"}]) is None
    assert find_grch37_mapping([]) is None


def test_is_genotype_valid():
    assert is_genotype_valid("CC", ["C", "T"]) is True
    assert is_genotype_valid("CT", ["C", "T"]) is True
    assert is_genotype_valid("GG", ["C", "T"]) is False


def test_is_genotype_valid_rejects_multi_character_alleles():
    # A genotype must match a whole allele, not just be built from letters
    # that happen to appear somewhere in the allele list. "AG" is not a valid
    # combination of the alleles "AT"/"GC" even though A and G each appear in
    # one of them.
    assert is_genotype_valid("AG", ["AT", "GC"]) is False


def test_is_genotype_valid_rejects_indel_style_alleles():
    # "-" marks "no sequence" (a deletion); it isn't a comparable base.
    assert is_genotype_valid("TT", ["T", "-"]) is False


def test_convert_row_ok():
    input_row = {"rsid": "rs9701055", "genotype": "CC"}
    variant_data = make_variant_data([make_mapping(strand=1, allele_string="C/T")])

    output_row = convert_row(input_row, variant_data)

    assert output_row == {
        "rsid": "rs9701055",
        "chromosome": "1",
        "position": 565433,
        "genotype": "CC",
        "status": Status.OK,
    }


def test_convert_row_unmapped_when_no_variant_data():
    input_row = {"rsid": "rsMISSING", "genotype": "CC"}

    output_row = convert_row(input_row, None)

    assert output_row == {
        "rsid": "rsMISSING",
        "chromosome": "",
        "position": "",
        "genotype": "CC",
        "status": Status.UNMAPPED,
    }


def test_convert_row_unmapped_when_no_grch37_mapping():
    input_row = {"rsid": "rs123", "genotype": "CC"}
    variant_data = make_variant_data([{"assembly_name": "GRCh38"}])

    output_row = convert_row(input_row, variant_data)

    assert output_row["status"] == Status.UNMAPPED
    assert output_row["chromosome"] == ""
    assert output_row["position"] == ""


def test_convert_row_invalid_includes_allele_string_and_var_class():
    input_row = {"rsid": "rs797044837", "genotype": "II"}
    variant_data = make_variant_data(
        [make_mapping(strand=1, allele_string="T/-")], var_class="deletion"
    )

    output_row = convert_row(input_row, variant_data)

    assert output_row["status"] == Status.INVALID
    assert output_row["allele_string"] == "T/-"
    assert output_row["var_class"] == "deletion"


def test_convert_row_reverse_complements_on_minus_strand():
    # allele_string "A/G" on the -1 strand becomes T/C on the forward strand,
    # so a forward-strand genotype of TC should be valid, and AG should not.
    input_row = {"rsid": "rsMINUS", "genotype": "TC"}
    variant_data = make_variant_data([make_mapping(strand=-1, allele_string="A/G")])

    assert convert_row(input_row, variant_data)["status"] == Status.OK

    invalid_row = {"rsid": "rsMINUS", "genotype": "AG"}
    assert convert_row(invalid_row, variant_data)["status"] == Status.INVALID
