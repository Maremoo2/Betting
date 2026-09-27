# HBI canonical data contract

The database, not a spreadsheet, is the source of truth.

## Core invariants

1. Every race has one stable `race_id`.
2. Every runner has a stable `selection_id` within the race.
3. Every market observation has an explicit timezone-aware timestamp.
4. Historical market snapshots are append-only.
5. Production predictions are frozen once persisted.
6. A feature/source timestamp may never be later than the prediction decision time.
7. Fundamental probabilities are stored separately from market probabilities.
8. Decision price, expected close, actual close and settlement price are distinct concepts.
9. Google Sheets is a read-oriented mirror/export layer only.

## Race-card JSON

```json
{
  "races": [
    {
      "race": {
        "race_id": "SE-SOLVALLA-2026-09-27-5",
        "race_date": "2026-09-27",
        "country": "SE",
        "track": "SOLVALLA",
        "race_no": 5,
        "start_time_utc": "2026-09-27T18:30:00+00:00",
        "discipline": "trot",
        "distance_m": 2140,
        "start_method": "auto",
        "race_class": "example",
        "created_at_utc": "2026-09-27T08:00:00+00:00"
      },
      "runners": []
    }
  ]
}
```

## Market-snapshot JSON

```json
{
  "snapshots": [
    {
      "race_id": "SE-SOLVALLA-2026-09-27-5",
      "selection_id": "7",
      "captured_at": "2026-09-27T18:25:00+00:00",
      "odds_decimal": 5.4,
      "pool_size": 125000,
      "market_regime": "ATG_TOTE",
      "information_cutoff_phase": "T-5"
    }
  ]
}
```

A provider adapter should preserve the provider's actual observation timestamp. The
collector timestamp is not a substitute when the provider exposes a more precise
market timestamp.

## Result JSON

```json
{
  "results": [
    {
      "race_id": "SE-SOLVALLA-2026-09-27-5",
      "winner_selection_id": "7",
      "settled_at": "2026-09-27T18:38:00+00:00",
      "actual_close_price": 4.8
    }
  ]
}
```

## Future provider adapters

Provider-specific code must map into these canonical structures. Provider parsing,
authentication and rate limits stay outside the modelling layer.
