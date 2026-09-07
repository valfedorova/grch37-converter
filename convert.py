from enum import StrEnum
from typing import TypedDict


class Status(StrEnum):
    OK = "OK"
    UNMAPPED = "UNMAPPED"
    INVALID = "INVALID"


class InputRow(TypedDict):
    rsid: str
    genotype: str


class OutputRow(TypedDict, total=False):
    rsid: str
    chromosome: str
    position: str
    genotype: str
    status: Status
    allele_string: str
    var_class: str


GRCH37_ASSEMBLY_NAME = "GRCh37"


def find_grch37_mapping(mappings: list[dict]) -> dict | None:
    for mapping in mappings:
        if mapping.get("assembly_name") == GRCH37_ASSEMBLY_NAME:
            return mapping
    return None


COMPLEMENT_BASES = {"A": "T", "T": "A", "C": "G", "G": "C"}


def reverse_complement(sequence: str) -> str:
    return "".join(COMPLEMENT_BASES[base] for base in reversed(sequence))


def is_genotype_valid(genotype: str, alleles: list[str]) -> bool:
    # This check only makes sense for true single-base SNP alleles: each
    # genotype character is independently compared against the set of
    # possible bases at this position. It does NOT generalize to indels or
    # multi-nucleotide alleles (e.g. "AT/GC"), where a genotype must match
    # one whole allele, not just be built from letters that appear somewhere
    # in the allele list. 23andMe-style indel genotypes ("I"/"D"/"--") can't
    # be validated from rsid + genotype alone anyway: 23andMe doesn't record
    # the actual bases involved, so a real answer requires an external indel
    # reference database. So: anything that isn't a set of single-base
    # alleles is deliberately treated as unable to validate, i.e. invalid.
    if any(len(allele) != 1 or allele == "-" for allele in alleles):
        return False

    # An empty genotype would pass the all() below vacuously and be reported as
    # a successful conversion. There is nothing to validate here, so it isn't
    # one. (No assumption is made about how long a non-empty genotype should
    # be: calls are diploid in most of the genome but single-base in others,
    # and the distinction isn't ours to hard-code.)
    if not genotype:
        return False

    allowed_bases = set(alleles)
    return all(base in allowed_bases for base in genotype)


def convert_row(input_row: InputRow, variant_data: dict | None) -> OutputRow:
    rsid = input_row["rsid"]
    genotype = input_row["genotype"]

    mappings = (variant_data or {}).get("mappings", [])
    mapping = find_grch37_mapping(mappings)

    if mapping is None:
        return {
            "rsid": rsid,
            "chromosome": "",
            "position": "",
            "genotype": genotype,
            "status": Status.UNMAPPED,
        }

    chromosome = mapping["seq_region_name"]
    position = mapping["start"]
    strand = mapping["strand"]
    alleles = mapping["allele_string"].split("/")

    # Ensembl reports alleles relative to the mapping's strand. Our genotype
    # calls are always forward-strand, so on a -1 strand mapping we need the
    # reverse complement of the alleles before comparing them to the genotype.
    if strand == -1:
        alleles = [reverse_complement(allele) for allele in alleles]

    if not is_genotype_valid(genotype, alleles):
        return {
            "rsid": rsid,
            "chromosome": chromosome,
            "position": position,
            "genotype": genotype,
            "status": Status.INVALID,
            "allele_string": mapping["allele_string"],
            "var_class": (variant_data or {}).get("var_class", ""),
        }

    return {
        "rsid": rsid,
        "chromosome": chromosome,
        "position": position,
        "genotype": genotype,
        "status": Status.OK,
    }
