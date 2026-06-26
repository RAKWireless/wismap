# WisMAP `/api/v1/validate` test fixtures

This directory ships canonical request/response pairs for the WisMAP v1 validate
endpoint. The WisBlock Code Generator's CI vendors these fixtures to detect
contract drift between releases.

## Layout

```
tests/fixtures/
├── README.md          ← this file
├── _generate.py       ← regenerates the fixtures from the in-repo wismap.core
└── validate/
    ├── 01-valid-clean.json
    ├── 02-i2c-collision.json
    ├── …
    └── 15-coreless-base-with-core-entry-422.json
```

## Fixture file format

Each fixture is a self-contained JSON object:

```json
{
  "name":              "01-valid-clean",
  "description":       "Two compatible I2C sensors on a standard base — no conflicts.",
  "request":           { "core": "RAK4631", "base": "RAK19007", "slots": [ … ] },
  "expected_status":   200,
  "expected_response": { "valid": true, "conflicts": [], …  }
}
```

- `request` is exactly what your client POSTs to `/api/v1/validate`.
- `expected_status` is the integer HTTP status WisMAP returns.
- `expected_response` is the JSON body — for 200 cases this is the full
  `ValidateResponse` (incl. the `resolved` block and the frontend-extension
  fields); for 4xx cases it is the spec's standard error envelope
  (`{"error": {"code": "…", "message": "…"}}`).

## How to use these in CI

A minimal Python consumer test looks like:

```python
import json, pathlib, requests

BASE = "https://api.wismap.example"   # or your local instance

for f in pathlib.Path("vendor/wismap-fixtures/validate").glob("*.json"):
    case = json.loads(f.read_text())
    r = requests.post(f"{BASE}/api/v1/validate", json=case["request"])
    assert r.status_code == case["expected_status"], f"{case['name']}: status"
    # For 200 responses the spec promises forward-compatible additions —
    # compare on the keys you actually depend on rather than full equality:
    body = r.json()
    expected = case["expected_response"]
    if r.status_code == 200:
        assert body["valid"] == expected["valid"], f"{case['name']}: valid flag"
        assert [c["code"] for c in body["conflicts"]] == \
               [c["code"] for c in expected["conflicts"]], f"{case['name']}: conflict codes"
    else:
        assert body["error"]["code"] == expected["error"]["code"], f"{case['name']}: error code"
```

Full-document `assertEqual(body, expected)` is **not recommended** — per the
versioning policy, WisMAP may add new fields to a response
within a major version, which would break exact-equality assertions. Compare
on the contract you depend on.

## Coverage

| # | Scenario | HTTP | `valid` | Highlights |
|---|---|---|---|---|
| 01 | Clean valid config | 200 | `true` | Two I2C sensors on different default addresses |
| 02 | I2C address collision | 200 | `false` | `code: i2c_address_collision` |
| 03 | Collision resolved by `i2c_address_overrides` | 200 | `true` | Same modules as 02, jumper override |
| 04 | Multiple structured conflicts | 200 | `false` | I2C + SPI_CS contention in one response |
| 05 | Power-pin warning (non-blocking) | 200 | `true` | `warnings[]` populated, `valid` still true |
| 06 | Slot incompatibility | 200 | `false` | Sensor in IO slot — `code: slot_incompatibility` |
| 07 | Unknown module | 200 | `false` | `code: unknown_module` |
| 08 | Duplicate slot in `slots[]` | 422 | n/a | `code: duplicate_slot` |
| 09 | CORE-in-slots matches top-level (tolerated) | 200 | `true` | Duplicate silently dropped |
| 10 | CORE-in-slots disagrees with top-level | 422 | n/a | `code: duplicate_slot` |
| 11 | Top-level `core` missing on a CORE-bearing base | 400 | n/a | `code: invalid_request` |
| 12 | Unknown top-level core | 404 | n/a | `code: core_not_found` |
| 13 | Unknown base | 404 | n/a | `code: base_not_found` |
| 14 | Coreless base (RAK6421 Pi Hat), `core` omitted | 200 | `true` | `resolved.core: null`, `resolved.lorawan: null` |
| 15 | Coreless base + CORE entry in `slots[]` | 422 | n/a | `code: duplicate_slot` |

## Regenerating

Fixtures are derived from the live `wismap.core` implementation. Whenever
WisMAP's catalog, rules, or validation logic change, re-run:

```bash
python tests/fixtures/_generate.py
```

This rewrites every file under `validate/` based on the current code. Commit
the regenerated fixtures alongside the change so consumers' CI catches the
delta on next vendor update.
