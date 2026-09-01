"""Tests for the dataset validator.

These use the small fixture CSVs in fixtures/ and never touch Postgres, so
they run without docker compose up. The database write path is exercised by
running `python -m ml.seed` against the real database.
"""

from pathlib import Path

import pytest

from ml.seed import read_csv, validate_all

FIXTURES = Path(__file__).parent / "fixtures"


def validate_fixture(name: str) -> list[str]:
    """Read one fixture directory and return every validation error."""
    directory = FIXTURES / name
    return validate_all(
        read_csv(directory / "destinations.csv"),
        read_csv(directory / "destination_factors.csv"),
        read_csv(directory / "region_pressure_history.csv"),
    )


def test_good_file_passes_validation() -> None:
    assert validate_fixture("good") == []


def test_missing_source_ref_fails() -> None:
    errors = validate_fixture("missing_source_ref")
    assert len(errors) == 1
    # The message names the file and the line, so the fix is obvious.
    assert errors[0] == "destination_factors.csv line 3: source_ref is empty"


def test_factor_value_of_150_fails() -> None:
    errors = validate_fixture("factor_out_of_range")
    assert len(errors) == 1
    assert errors[0] == (
        "destination_factors.csv line 3: environmental is 150.0, "
        "must be between 0 and 100"
    )


def test_committed_dataset_is_valid() -> None:
    """The CSVs in ml/data must always pass. This is the check that catches a
    bad hand-edit before it reaches the database."""
    data_dir = Path(__file__).parents[1] / "data"
    errors = validate_all(
        read_csv(data_dir / "destinations.csv"),
        read_csv(data_dir / "destination_factors.csv"),
        read_csv(data_dir / "region_pressure_history.csv"),
    )
    assert errors == []


@pytest.mark.parametrize(
    ("column", "value", "expected"),
    [
        ("lat", "48.85", "destinations.csv line 2: lat 48.85 is outside Sri Lanka"),
        ("lon", "2.35", "destinations.csv line 2: lon 2.35 is outside Sri Lanka"),
    ],
)
def test_coordinates_outside_sri_lanka_fail(
    column: str, value: str, expected: str
) -> None:
    destinations = read_csv(FIXTURES / "good" / "destinations.csv")
    destinations.loc[0, column] = value

    errors = validate_all(
        destinations,
        read_csv(FIXTURES / "good" / "destination_factors.csv"),
        read_csv(FIXTURES / "good" / "region_pressure_history.csv"),
    )
    assert len(errors) == 1
    assert errors[0].startswith(expected)


def test_duplicate_destination_name_fails() -> None:
    destinations = read_csv(FIXTURES / "good" / "destinations.csv")
    destinations.loc[1, "name"] = "Belihuloya"

    errors = validate_all(
        destinations,
        read_csv(FIXTURES / "good" / "destination_factors.csv"),
        read_csv(FIXTURES / "good" / "region_pressure_history.csv"),
    )
    assert any("duplicate destination name 'Belihuloya'" in error for error in errors)


def test_bad_confidence_value_fails() -> None:
    factors = read_csv(FIXTURES / "good" / "destination_factors.csv")
    factors.loc[0, "confidence"] = "probably"

    errors = validate_all(
        read_csv(FIXTURES / "good" / "destinations.csv"),
        factors,
        read_csv(FIXTURES / "good" / "region_pressure_history.csv"),
    )
    assert len(errors) == 1
    assert "confidence is 'probably'" in errors[0]


def test_destination_with_no_factor_row_fails() -> None:
    """M1 is not reached until every destination has its factor values."""
    factors = read_csv(FIXTURES / "good" / "destination_factors.csv")

    errors = validate_all(
        read_csv(FIXTURES / "good" / "destinations.csv"),
        factors.iloc[:1],
        read_csv(FIXTURES / "good" / "region_pressure_history.csv"),
    )
    assert errors == [
        "destination_factors.csv: no row for destination 'Meemure'"
    ]
