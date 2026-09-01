# Dataset

Three CSVs, loaded into Postgres by `python -m ml.seed`.

> **The three rows currently in each file are examples, not data.** They exist
> to show the column format and to give the loader something to run against.
> Every number in them is made up and every `source_ref` says so. They must all
> be replaced before the demo. A judge will ask where a value came from, and
> "it was in the template" is not an answer.

## Files

| File | One row is | Loads into |
|---|---|---|
| `destinations.csv` | A destination | `destinations` |
| `destination_factors.csv` | The five factor values for one destination | `destination_factors` |
| `region_pressure_history.csv` | One region in one month | `region_pressure_history` |

`destination_factors.csv` and `destinations.csv` are joined on `name`, so the
names must match exactly. Every destination needs a factor row; the loader
rejects the dataset if one is missing.

## Column notes

- `activities` is a **semicolon**-separated list inside a single CSV field:
  `hiking;waterfalls;cycling`. A semicolon rather than a comma so the file
  still opens cleanly in a spreadsheet.
- `lat` and `lon` are decimal degrees and must fall inside Sri Lanka
  (5.9–9.9 N, 79.6–81.9 E).
- The five factor values are 0–100.
- `source_ref` is free text but must not be empty. Write enough that someone
  else can find the number again: publication, year, and table or page.
- `confidence` is exactly `measured` or `estimated`. Use `measured` when the
  value came from a published figure, `estimated` when it came from a proxy or
  a judgement call.

## Sources

These are the sources named in `plan.md` section 3. Fill in the exact report
or query for each value as it is collected, and copy that into the row's
`source_ref`.

### Sri Lanka Tourism Development Authority (SLTDA)

- <https://www.sltda.gov.lk/en/statistical-reports>

Annual and monthly statistical reports. Taken from here: monthly occupancy
rate, tourist arrivals and guest nights per province, which become
`region_pressure_history` and the training data for the pressure model. Also
the basis for the `crowd` factor.

Record the report year and the table number in `source_ref`, because the table
numbering changes between editions.

### Open-Meteo — Historical Weather API

- <https://open-meteo.com/en/docs/historical-weather-api>

Free for non-commercial use, no API key. Taken from here: monthly temperature
and rainfall means per destination coordinate, used for the `environmental`
factor and as a similarity attribute.

Record the date range and the coordinates queried.

### OpenAQ

- <https://openaq.org>
- API docs: <https://docs.openaq.org>

Air quality measurements. Taken from here: whatever sensor coverage exists near
each destination, feeding the `environmental` factor.

**Coverage outside Colombo is thin.** `plan.md` section 3 and the risk table
both flag this. Where there is no nearby sensor, the value is a proxy and the
row must be marked `estimated`, with `source_ref` saying what the proxy was.

### Values with no published source

`community`, `infrastructure` and `suitability` have no single dataset behind
them. Where a value is scored by hand or derived from a proxy such as district
road density, mark the row `estimated` and write the reasoning into
`source_ref`.

## Licences

Any dataset used here also gets a row in the repository's `THIRD_PARTY.md`
with its licence, the same as a code dependency (Guidelines 7.3).
