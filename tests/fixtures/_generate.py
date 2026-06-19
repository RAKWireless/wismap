#!/usr/bin/env python3
"""
Generate canonical /api/v1/validate fixtures.

Each fixture is one JSON file with:
  {
    "name":        short-kebab-case identifier (filename matches),
    "description": one-line human summary,
    "request":     POST body sent to /api/v1/validate,
    "expected_status":   integer HTTP status the server returns,
    "expected_response": JSON body the server returns,
  }

Run from repo root with `python tests/fixtures/_generate.py`. Re-run whenever
WisMAP catalog or validation logic changes — fixtures are derived from the
current implementation by design.
"""
import json
import os
import sys

# Make sure we import the in-repo wismap package.
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

from wismap.core import load_data_v1, validate_v1, solve_v1


def _write(subdir, name, description, request, status, expected_response):
    path = os.path.join(HERE, subdir, f"{name}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({
            "name": name,
            "description": description,
            "request": request,
            "expected_status": status,
            "expected_response": expected_response,
        }, f, indent=2)
    print(f"wrote {path}  (status={status})")


def run(name, description, request, definitions, config, rules):
    """Execute one fixture against validate_v1, render the case file."""
    response, err, status = validate_v1(definitions, config, rules, request)
    if err is not None:
        code, message = err
        expected_response = {"error": {"code": code, "message": message}}
    else:
        expected_response = response
    _write("validate", name, description, request, status, expected_response)


def run_solve(name, description, request, definitions, config, rules, compat):
    """Execute one fixture against solve_v1, render the case file."""
    response, err, status = solve_v1(definitions, config, rules, compat, request)
    if err is not None:
        code, message = err
        expected_response = {"error": {"code": code, "message": message}}
    else:
        expected_response = response
    _write("solve", name, description, request, status, expected_response)


def main():
    definitions, config, rules, compat = load_data_v1(os.path.join(REPO, "data"))

    # 200 — clean configuration
    run("01-valid-clean", "Two compatible I2C sensors on a standard base — no conflicts.", {
        "core": "RAK4631",
        "base": "RAK19007",
        "slots": [
            {"slot": "SENSOR_A", "module": "RAK1901"},
            {"slot": "SENSOR_B", "module": "RAK1902"},
        ],
    }, definitions, config, rules)

    # 200, valid=false — I2C address collision
    run("02-i2c-collision", "Same module placed twice; default I2C addresses collide.", {
        "core": "RAK4631",
        "base": "RAK19007",
        "slots": [
            {"slot": "SENSOR_A", "module": "RAK1901"},
            {"slot": "SENSOR_C", "module": "RAK1901"},
        ],
    }, definitions, config, rules)

    # 200, valid=true — collision resolved by jumper override
    run("03-i2c-collision-resolved-by-override",
        "Same module twice but a jumper override moves one to 0x71 — valid.", {
        "core": "RAK4631",
        "base": "RAK19007",
        "slots": [
            {"slot": "SENSOR_A", "module": "RAK1901"},
            {"slot": "SENSOR_C", "module": "RAK1901"},
        ],
        "options": {"i2c_address_overrides": {"RAK1901@SENSOR_C": "0x71"}},
    }, definitions, config, rules)

    # 200, valid=false — multiple structured conflicts in one response
    # (I2C address collision + SPI_CS pin contention from the same misconfig).
    run("04-multiple-conflicts",
        "Two RAK12500 GNSS modules — both default to I2C 0x42 and both drive SPI_CS.", {
        "core": "RAK4631",
        "base": "RAK19007",
        "slots": [
            {"slot": "SENSOR_A", "module": "RAK12500"},
            {"slot": "SENSOR_C", "module": "RAK12500"},
        ],
    }, definitions, config, rules)

    # 200, valid=true with a warning — 3V3_S/IO2 power-enable advisory
    run("05-power-pin-warning",
        "RAK12500 uses the 3V3_S rail; IO2 is the rail's enable — yields a warning.", {
        "core": "RAK4631",
        "base": "RAK19007",
        "slots": [
            {"slot": "SENSOR_A", "module": "RAK12500"},
        ],
    }, definitions, config, rules)

    # 200, valid=false — slot_incompatibility
    run("06-slot-incompatibility", "Sensor module placed in an IO slot.", {
        "core": "RAK4631",
        "base": "RAK19007",
        "slots": [
            {"slot": "IO_A", "module": "RAK1901"},
        ],
    }, definitions, config, rules)

    # 200, valid=false — unknown_module
    run("07-unknown-module", "Module id not in WisMAP catalog.", {
        "core": "RAK4631",
        "base": "RAK19007",
        "slots": [
            {"slot": "SENSOR_A", "module": "RAK9999"},
        ],
    }, definitions, config, rules)

    # 422 — duplicate slot
    run("08-duplicate-slot-422", "Same slot id appears twice in slots[].", {
        "core": "RAK4631",
        "base": "RAK19007",
        "slots": [
            {"slot": "SENSOR_A", "module": "RAK1901"},
            {"slot": "SENSOR_A", "module": "RAK1902"},
        ],
    }, definitions, config, rules)

    # 200 — CORE in slots[] matches top-level core (tolerated, silently dropped)
    run("09-core-in-slots-matching",
        "CORE entry in slots[] matches the top-level core — tolerated.", {
        "core": "RAK4631",
        "base": "RAK19007",
        "slots": [
            {"slot": "CORE", "module": "RAK4631"},
            {"slot": "SENSOR_A", "module": "RAK1901"},
        ],
    }, definitions, config, rules)

    # 422 — CORE in slots[] disagrees with top-level
    run("10-core-in-slots-disagreeing-422",
        "CORE entry in slots[] disagrees with top-level core.", {
        "core": "RAK4631",
        "base": "RAK19007",
        "slots": [
            {"slot": "CORE", "module": "RAK11310"},
            {"slot": "SENSOR_A", "module": "RAK1901"},
        ],
    }, definitions, config, rules)

    # 400 — core missing for a base that requires it
    run("11-core-missing-400", "Standard base with no top-level core supplied.", {
        "base": "RAK19007",
        "slots": [],
    }, definitions, config, rules)

    # 404 — unknown core
    run("12-unknown-core-404", "Top-level core id not in WisMAP catalog.", {
        "core": "RAK9999",
        "base": "RAK19007",
        "slots": [],
    }, definitions, config, rules)

    # 404 — unknown base
    run("13-unknown-base-404", "Base id not in WisMAP catalog.", {
        "core": "RAK4631",
        "base": "RAK9999",
        "slots": [],
    }, definitions, config, rules)

    # 200 — coreless base (Pi Hat), core omitted
    run("14-coreless-base-pi-hat",
        "RAK6421 Pi Hat has no CORE slot; core may be omitted.", {
        "base": "RAK6421",
        "slots": [
            {"slot": "SENSOR_A", "module": "RAK1901"},
        ],
    }, definitions, config, rules)

    # 422 — CORE entry on coreless base
    run("15-coreless-base-with-core-entry-422",
        "RAK6421 has no CORE slot; including one in slots[] is rejected.", {
        "base": "RAK6421",
        "slots": [
            {"slot": "CORE", "module": "RAK4631"},
        ],
    }, definitions, config, rules)

    # ── /api/v1/solve fixtures (spec 010) ──────────────────────────────────

    # 200 — clean full fit
    run_solve("01-clean-fit",
        "Two compatible sensors — both placed, rank-1 valid.", {
        "core": "RAK4631", "base": "RAK19007",
        "modules": ["RAK1901", "RAK1902"],
    }, definitions, config, rules, compat)

    # 200 — over-capacity: more sensors than sensor slots → best partial
    run_solve("02-over-capacity",
        "Five sensors on a 4-sensor-slot base; one is unplaced (no_free_slot).", {
        "core": "RAK4631", "base": "RAK19007",
        "modules": ["RAK1901", "RAK1902", "RAK1903", "RAK1904", "RAK12500"],
    }, definitions, config, rules, compat)

    # 200 — unknown + base-incompatible modules reported, rest still solved
    run_solve("03-incompatible",
        "Unknown id + a WisPower module (no POWER slot on RAK19007) — both unplaced; RAK1901 placed.", {
        "core": "RAK4631", "base": "RAK19007",
        "modules": ["RAK9999", "RAK19012", "RAK1901"],
    }, definitions, config, rules, compat)

    # 200 — coreless base, core omitted
    run_solve("04-coreless",
        "RAK6421 Pi Hat has no CORE slot; core may be omitted.", {
        "base": "RAK6421",
        "modules": ["RAK1901"],
    }, definitions, config, rules, compat)

    # 200 — tie-heavy input locks a deterministic rank order
    run_solve("05-tie-order",
        "Two distinct sensors, symmetric placements; deterministic tiebreak fixes the order.", {
        "core": "RAK4631", "base": "RAK19007",
        "modules": ["RAK1901", "RAK1902"], "max_solutions": 5,
    }, definitions, config, rules, compat)

    # 200 — enumeration cap tripped → truncated:true (best-effort), deterministic
    big = [m.upper() for m, d in definitions.items()
           if d.get("type") == "WisSensor" and "RAK19011" in compat.get(m, {})][:8]
    run_solve("06-cap-hit",
        "Eight sensors on a large base trips the node cap → truncated, best-effort.", {
        "core": "RAK4631", "base": "RAK19011", "modules": big,
    }, definitions, config, rules, compat)

    # 200 — top-layer tiebreak: a single sensor ranks top slots above bottom
    run_solve("07-top-layer-tiebreak",
        "One sensor on RAK19007; top-layer placements (A/B) outrank bottom (C/D).", {
        "core": "RAK4631", "base": "RAK19007",
        "modules": ["RAK1901"], "max_solutions": 5,
    }, definitions, config, rules, compat)

    # 200 — max_solutions clamped to 5
    run_solve("08-max-solutions",
        "Four sensors yield many layouts; max_solutions=99 is clamped to 5.", {
        "core": "RAK4631", "base": "RAK19007",
        "modules": ["RAK1901", "RAK1902", "RAK1903", "RAK1904"], "max_solutions": 99,
    }, definitions, config, rules, compat)

    # 200, every layout invalid — the same module twice collides on I2C; the
    # solution carries the *reason* (conflicts[]), not just error_count.
    run_solve("09-conflict-reasons",
        "Same sensor twice — all placements collide on I2C; conflicts[] explains why.", {
        "core": "RAK4631", "base": "RAK19007",
        "modules": ["RAK1901", "RAK1901"],
    }, definitions, config, rules, compat)


if __name__ == "__main__":
    main()
