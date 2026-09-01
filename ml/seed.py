"""Load the compiled dataset from CSV into Postgres.

Run with:

    python -m ml.seed

Validation happens first, across all three files. If anything fails, every
problem is printed with its file and line number and nothing at all is written
to the database. That matters because a half-loaded dataset is harder to
notice than an empty one.

Re-running is safe. Destinations are matched by name, and the other two tables
upsert on their primary keys, so the script can be run again after a fix
without producing duplicates.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from api.database import SessionLocal
from api.models import Destination, DestinationFactor, RegionPressureHistory

DATA_DIR = Path(__file__).parent / "data"

# Sri Lanka bounding box. Anything outside this is a typo, not a destination.
LAT_MIN, LAT_MAX = 5.9, 9.9
LON_MIN, LON_MAX = 79.6, 81.9

FACTOR_COLUMNS = [
    "environmental",
    "community",
    "crowd",
    "infrastructure",
    "suitability",
]

# plan.md section 7: confidence is one of exactly these two.
ALLOWED_CONFIDENCE = ("measured", "estimated")

# activities is a list column, so the values are separated inside the CSV
# field. A semicolon is used rather than a comma so the file stays easy to
# edit by hand in a spreadsheet.
ACTIVITY_SEPARATOR = ";"

DESTINATION_COLUMNS = [
    "name",
    "lat",
    "lon",
    "district",
    "region",
    "landscape_type",
    "activities",
    "cost_band",
    "typical_days",
]
FACTOR_FILE_COLUMNS = ["name", *FACTOR_COLUMNS, "source_ref", "confidence"]
HISTORY_COLUMNS = [
    "region",
    "year",
    "month",
    "occupancy_rate",
    "arrivals",
    "guest_nights",
]


def read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV with every column as a plain string.

    keep_default_na=False stops pandas turning an empty source_ref into NaN,
    so a blank cell stays an empty string and the "non-empty" check below can
    actually see it. Numbers are converted explicitly later, which means a
    non-numeric value produces a readable error instead of a crash.
    """
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _line(index: int) -> int:
    """CSV line number for a dataframe row. Row 0 is line 2, after the header."""
    return index + 2


def _missing_columns(df: pd.DataFrame, expected: list[str], filename: str) -> list[str]:
    missing = [column for column in expected if column not in df.columns]
    if missing:
        return [f"{filename}: missing required column(s): {', '.join(missing)}"]
    return []


def _number(value: str) -> float | None:
    """Parse a numeric cell, or None if it is blank or not a number."""
    try:
        return float(value.strip())
    except (ValueError, AttributeError):
        return None


def validate_destinations(df: pd.DataFrame) -> list[str]:
    errors = _missing_columns(df, DESTINATION_COLUMNS, "destinations.csv")
    if errors:
        return errors

    seen_names: dict[str, int] = {}

    for index, row in df.iterrows():
        line = _line(int(index))
        where = f"destinations.csv line {line}"

        name = row["name"].strip()
        if not name:
            errors.append(f"{where}: name is empty")
        elif name in seen_names:
            errors.append(
                f"{where}: duplicate destination name {name!r}, "
                f"already used on line {seen_names[name]}"
            )
        else:
            seen_names[name] = line

        lat = _number(row["lat"])
        if lat is None:
            errors.append(f"{where}: lat {row['lat']!r} is not a number")
        elif not LAT_MIN <= lat <= LAT_MAX:
            errors.append(
                f"{where}: lat {lat} is outside Sri Lanka "
                f"({LAT_MIN} to {LAT_MAX})"
            )

        lon = _number(row["lon"])
        if lon is None:
            errors.append(f"{where}: lon {row['lon']!r} is not a number")
        elif not LON_MIN <= lon <= LON_MAX:
            errors.append(
                f"{where}: lon {lon} is outside Sri Lanka "
                f"({LON_MIN} to {LON_MAX})"
            )

        for column in ("district", "region", "landscape_type", "cost_band"):
            if not row[column].strip():
                errors.append(f"{where}: {column} is empty")

        if not _activities(row["activities"]):
            errors.append(f"{where}: activities is empty")

        typical_days = _number(row["typical_days"])
        if typical_days is None:
            errors.append(
                f"{where}: typical_days {row['typical_days']!r} is not a number"
            )
        elif typical_days < 1:
            errors.append(f"{where}: typical_days {typical_days} must be at least 1")

    return errors


def validate_factors(df: pd.DataFrame, destination_names: set[str]) -> list[str]:
    errors = _missing_columns(df, FACTOR_FILE_COLUMNS, "destination_factors.csv")
    if errors:
        return errors

    seen_names: dict[str, int] = {}

    for index, row in df.iterrows():
        line = _line(int(index))
        where = f"destination_factors.csv line {line}"

        name = row["name"].strip()
        if not name:
            errors.append(f"{where}: name is empty")
        elif name in seen_names:
            errors.append(
                f"{where}: duplicate destination name {name!r}, "
                f"already used on line {seen_names[name]}"
            )
        else:
            seen_names[name] = line
            if name not in destination_names:
                errors.append(
                    f"{where}: {name!r} is not in destinations.csv"
                )

        for column in FACTOR_COLUMNS:
            value = _number(row[column])
            if value is None:
                errors.append(f"{where}: {column} {row[column]!r} is not a number")
            elif not 0 <= value <= 100:
                errors.append(
                    f"{where}: {column} is {value}, must be between 0 and 100"
                )

        # Not optional. This is the answer when a judge asks where a number
        # came from (plan.md section 8).
        if not row["source_ref"].strip():
            errors.append(f"{where}: source_ref is empty")

        confidence = row["confidence"].strip()
        if confidence not in ALLOWED_CONFIDENCE:
            errors.append(
                f"{where}: confidence is {confidence!r}, must be one of "
                f"{' or '.join(repr(c) for c in ALLOWED_CONFIDENCE)}"
            )

    # M1 is not reached until every destination has its factor values, so a
    # destination with no row here is an error rather than a silent gap.
    for name in sorted(destination_names - set(seen_names)):
        errors.append(
            f"destination_factors.csv: no row for destination {name!r}"
        )

    return errors


def validate_history(df: pd.DataFrame) -> list[str]:
    errors = _missing_columns(df, HISTORY_COLUMNS, "region_pressure_history.csv")
    if errors:
        return errors

    seen_keys: dict[tuple[str, int, int], int] = {}

    for index, row in df.iterrows():
        line = _line(int(index))
        where = f"region_pressure_history.csv line {line}"

        region = row["region"].strip()
        if not region:
            errors.append(f"{where}: region is empty")

        year = _number(row["year"])
        if year is None:
            errors.append(f"{where}: year {row['year']!r} is not a number")

        month = _number(row["month"])
        if month is None:
            errors.append(f"{where}: month {row['month']!r} is not a number")
        elif not 1 <= month <= 12:
            errors.append(f"{where}: month is {month:g}, must be between 1 and 12")

        occupancy = _number(row["occupancy_rate"])
        if occupancy is None:
            errors.append(
                f"{where}: occupancy_rate {row['occupancy_rate']!r} is not a number"
            )
        elif not 0 <= occupancy <= 100:
            errors.append(
                f"{where}: occupancy_rate is {occupancy}, must be between 0 and 100"
            )

        for column in ("arrivals", "guest_nights"):
            value = _number(row[column])
            if value is None:
                errors.append(f"{where}: {column} {row[column]!r} is not a number")
            elif value < 0:
                errors.append(f"{where}: {column} is {value:g}, cannot be negative")

        if region and year is not None and month is not None:
            key = (region, int(year), int(month))
            if key in seen_keys:
                errors.append(
                    f"{where}: duplicate row for {region} "
                    f"{int(year)}-{int(month):02d}, "
                    f"already used on line {seen_keys[key]}"
                )
            else:
                seen_keys[key] = line

    return errors


def validate_all(
    destinations: pd.DataFrame,
    factors: pd.DataFrame,
    history: pd.DataFrame,
) -> list[str]:
    """Every problem in all three files, so one run shows the whole list."""
    errors = validate_destinations(destinations)

    names = set()
    if "name" in destinations.columns:
        names = {name.strip() for name in destinations["name"] if name.strip()}

    errors.extend(validate_factors(factors, names))
    errors.extend(validate_history(history))
    return errors


def _activities(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(ACTIVITY_SEPARATOR) if item.strip()]


def load(
    session: Session,
    destinations: pd.DataFrame,
    factors: pd.DataFrame,
    history: pd.DataFrame,
) -> dict[str, int]:
    """Write all three tables. Caller commits.

    Assumes validate_all returned no errors.
    """
    # destinations has a surrogate id, so there is nothing to ON CONFLICT on.
    # Matching by name is what makes a re-run update rather than duplicate.
    existing: dict[str, Destination] = {
        row.name: row for row in session.query(Destination).all()
    }

    inserted = 0
    updated = 0
    for _, row in destinations.iterrows():
        values: dict[str, Any] = {
            "name": row["name"].strip(),
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "district": row["district"].strip(),
            "region": row["region"].strip(),
            "landscape_type": row["landscape_type"].strip(),
            "activities": _activities(row["activities"]),
            "cost_band": row["cost_band"].strip(),
            "typical_days": int(float(row["typical_days"])),
        }
        destination = existing.get(values["name"])
        if destination is None:
            destination = Destination(**values)
            session.add(destination)
            existing[values["name"]] = destination
            inserted += 1
        else:
            for column, value in values.items():
                setattr(destination, column, value)
            updated += 1

    # Needed so newly inserted destinations have ids for the factor rows below.
    session.flush()

    name_to_id = {name: row.id for name, row in existing.items()}

    factor_rows = [
        {
            "destination_id": name_to_id[row["name"].strip()],
            **{column: float(row[column]) for column in FACTOR_COLUMNS},
            "source_ref": row["source_ref"].strip(),
            "confidence": row["confidence"].strip(),
        }
        for _, row in factors.iterrows()
    ]
    if factor_rows:
        statement = pg_insert(DestinationFactor).values(factor_rows)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=["destination_id"],
                set_={
                    column: statement.excluded[column]
                    for column in (*FACTOR_COLUMNS, "source_ref", "confidence")
                },
            )
        )

    history_rows = [
        {
            "region": row["region"].strip(),
            "year": int(float(row["year"])),
            "month": int(float(row["month"])),
            "occupancy_rate": float(row["occupancy_rate"]),
            "arrivals": int(float(row["arrivals"])),
            "guest_nights": int(float(row["guest_nights"])),
        }
        for _, row in history.iterrows()
    ]
    if history_rows:
        statement = pg_insert(RegionPressureHistory).values(history_rows)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=["region", "year", "month"],
                set_={
                    column: statement.excluded[column]
                    for column in ("occupancy_rate", "arrivals", "guest_nights")
                },
            )
        )

    return {
        "destinations_inserted": inserted,
        "destinations_updated": updated,
        "destination_factors": len(factor_rows),
        "region_pressure_history": len(history_rows),
    }


def print_summary(counts: dict[str, int], factors: pd.DataFrame) -> None:
    confidence = factors["confidence"].str.strip()
    measured = int((confidence == "measured").sum())
    estimated = int((confidence == "estimated").sum())
    total_destinations = (
        counts["destinations_inserted"] + counts["destinations_updated"]
    )

    print("Seed complete.")
    print(
        f"  destinations              {total_destinations:>5}"
        f"  ({counts['destinations_inserted']} inserted, "
        f"{counts['destinations_updated']} updated)"
    )
    print(f"  destination_factors       {counts['destination_factors']:>5}")
    print(f"  region_pressure_history   {counts['region_pressure_history']:>5}")
    print()
    print(f"  measured factor rows      {measured:>5}")
    print(f"  estimated factor rows     {estimated:>5}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load the CSV dataset into Postgres.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR,
        help="Directory holding the three CSVs (default: ml/data).",
    )
    args = parser.parse_args(argv)

    try:
        destinations = read_csv(args.data_dir / "destinations.csv")
        factors = read_csv(args.data_dir / "destination_factors.csv")
        history = read_csv(args.data_dir / "region_pressure_history.csv")
    except FileNotFoundError as exc:
        print(f"Cannot read dataset: {exc}", file=sys.stderr)
        return 1

    errors = validate_all(destinations, factors, history)
    if errors:
        print(
            f"Validation failed with {len(errors)} problem(s). "
            "Nothing was written to the database.",
            file=sys.stderr,
        )
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    session = SessionLocal()
    try:
        counts = load(session, destinations, factors, history)
        session.commit()
    except Exception:
        # Nothing partial survives a failure part way through the write.
        session.rollback()
        raise
    finally:
        session.close()

    print_summary(counts, factors)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
