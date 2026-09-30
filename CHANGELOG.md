Changelog
=========

All notable changes to this project will be documented in this file.


## 0.7.1 — 2026-09-30

A malformed pin role in the catalog no longer takes the combine path down with it.

### Fixed

* **A `null` pin role no longer crashes combine, `/api/v1/validate` or `/api/v1/solve`.**
  The rule checks do string work on every role, so a single `null` in a module's
  `mapping` turned every request touching that module into a 500. The vendored catalog
  cannot carry one today (wisblock-data's schema rejects it), but nothing in WisMAP
  enforced that. A `null` role is now treated exactly like an absent one, as is any other
  non-string role and a whole `mapping: null` or `naming: null`. This applies everywhere a
  role is read: the combine table, CLI `info`, and `pin_mapping` / `naming` on
  `GET /api/v1/{modules,cores,bases}/{id}`, which no longer echo a `null`. Output for the
  current catalog is unchanged.
* **`GET /api/v1/bases/{id}` no longer gains `naming.I2C_ADDR`** after its worker has
  served a combine, `/validate` or `/solve`. Building the combine table wrote that key
  into the loaded catalog's own `naming` dict, so the response depended on which worker
  answered and what it had served before. The key was never part of any base's data or of
  the OpenAPI document.

### Changed

* **Catalog synced from wisblock-data** (`50aa39f`):
  * `chip` corrected on RAK12008 (`Sensirion STC31`) and RAK12037 (`Sensirion SCD30`).
  * RAK12500 tags: `spi` replaced by `i2c` and `uart`.
  * RAK1921 I2C address corrected from `0x76` to `0x3C`.

  No consumer fixture moved.


## 0.7.0 — 2026-09-07

wisblock-data becomes the source of truth. The module catalog, the slot catalogue
and the conflict rules are no longer authored in this repository — they are
generated upstream from per-aspect module files and vendored here, so WisMAP and
the other consumers of that data can no longer disagree about a module.

### Added

* **`make sync-data`** — copies `dist/wismap/{definitions,config,rules}.yml` into `data/`,
  via `tools/sync-data.sh`. The upstream tree is either a checkout (`WISBLOCK_DATA`, default
  `../../wisblock-data`) or a clone (`WISBLOCK_DATA_REPO`, defaulting to
  `RAKWireless/wisblock-data`, at `WISBLOCK_DATA_REF`) when that path holds no `dist/wismap` —
  the second path is what lets a CI runner, or a machine that has never checked the upstream
  out, sync anyway.
* **`data/UPSTREAM`** — records the wisblock-data commit that produced the vendored files.
  Without it the catalog is anonymous: nothing in this repository says which version of the
  data it carries, which makes an automated sync unauditable. Rewritten only when an artifact
  actually moved, so a scheduled run that finds nothing new proposes nothing.
* **`.github/workflows/sync-data.yml`** — the automatic sync. Runs daily, on manual dispatch,
  and on a `wisblock-data-updated` repository dispatch so upstream can announce a build rather
  than being waited for. It syncs, regenerates the consumer fixtures, runs the drift guards, and
  opens a pull request on `chore/sync-wisblock-data` when anything changed. It never pushes to
  `master` — a catalog change alters what the API reports, so it goes through review.
  Needs `secrets.WISBLOCK_DATA_TOKEN` only while upstream is private — sharing an organisation
  does not let one repository's `GITHUB_TOKEN` read another's — and falls back to the built-in
  token once it is public. `secrets.SYNC_PR_TOKEN` is optional and only exists so that CI runs
  on the sync PR, which a `GITHUB_TOKEN` push cannot trigger.
* **`.github/workflows/ci.yml`** — this repository's first CI. Three drift guards on every PR
  and push to `master`: `check-data`, `check-fixtures`, `check-openapi`. `check-data` reports a
  notice and skips when wisblock-data cannot be checked out, as on a fork PR, rather than
  failing a build over something its author cannot fix.
* **`make check-data`** — asserts the three vendored files still match upstream, so a hand-edit
  or a half-finished sync is caught rather than shipped.
* **`make check-fixtures`** — regenerates `tests/fixtures/` and fails if anything moved, which
  catches a catalog or logic change shipped without telling the WisBlock Code Generator. It
  snapshots and compares rather than consulting `git diff`, so it answers the same on a CI
  runner and in a working tree with unrelated uncommitted changes.
* `chip` is now shown by `python wismap.py info` and returned by `get_module_info()`.
  The field went from 24 to 107 modules in this sync, which made its absence from the
  CLI conspicuous; the web UI already displayed it via `/api/v1/modules`.

### Changed

* **Catalog synced from wisblock-data**, 143 field-level changes:
  * `chip` authored for 83 more modules from RAK datasheet chipset tables (24 → 107).
  * **Pin roles `SDA1`/`SCL1` corrected to canonical `I2C1_SDA`/`I2C1_SCL`** on
    RAK13002/13003/13004/14001/14002/14003/14004/14014. The old spellings matched
    neither the module-role signal table nor the bus-family test, so all eight
    reported no I2C interface at all — seven of them while carrying an I2C address.
    `interfaces`, `signal_map` and `core_requirements` are now correct for them.
  * **Base `naming` keys corrected** on all 8 base boards: the generic function is now
    the key and the board-specific label the value (`UART1_RX: RXD1`), where both used
    to be the label (`RXD1: RXD1`). Because the key has to be a function the slot
    exposes, the base-board column of a combine table left every UART row blank; those
    cells now carry the board's own pin names.
  * RAK12017 corrected from a ToF sensor to the IR detection module it is
    (chip, description and tags).
  * Phantom I2C addresses dropped from RAK12031 and RAK13800; real ones added for
    RAK14009/14010/14011 (`0x5F`).
  * RAK6421 `IO_B` pin 17 is plain `3V3` — the `GPIO00` annotation was stray; there is
    no such net on the board, and the other three identically-positioned supply pins
    were already plain `3V3`.
  * Documentation URLs added for RAK19005 and RAK19008.
* `make check-openapi` no longer goes through `.venv/bin/activate`; it and the other
  guards run `$(PYTHON)`, which is the project virtualenv when there is one and `python3`
  otherwise. The same target now works locally and on a CI runner that installs into the
  system interpreter.
* `tests/fixtures/{validate,solve}/*.json` regenerated against the new catalog. Beyond
  the base-board UART cells, this also picks up the slot labels (`Core Slot`,
  `Sensor Slot A`, …) that moved from code into `config.yml` in 0.6.0 without the
  fixtures being refreshed at the time.

### Removed

* **`data/modules/<id>.yml`** (141 files) and **`make generate`** — the catalog is no
  longer authored here. A module fix is made upstream in wisblock-data, regenerated
  there, and synced.
* **`make import`, `python wismap.py import`, `python wismap.py clean`** and the cached
  `data/WisBlock-IO-Pin-Mapper.xlsx` — the RAK Pin-Mapper spreadsheet is upstream of
  wisblock-data, not of WisMAP, so the download-and-diff workflow has no consumer left.
  `openpyxl` drops out of `requirements.txt` with it.


## 0.6.0 — 2026-07-08

WisMAP's own data becomes the source of truth — the module catalog is decoupled
from the upstream RAK Pin-Mapper spreadsheet (spec 014).

### Added

* **`make generate` (`python wismap.py generate`)** — rebuilds `data/definitions.yml`
  by merging the per-module files under the new `data/modules/` directory. The
  generated catalog is byte-identical to the previous spreadsheet-plus-patch build,
  so runtime, the `/api/v1/*` contract, the CLI, and the frontend are unchanged.

### Changed

* **The module catalog is now authored as one full file per module under
  `data/modules/<id>.yml`** (141 files), replacing the spreadsheet-plus-partial-patch
  model. These files are the editable source of truth: edit a module and run
  `make generate` to refresh `data/definitions.yml`.
* **`make import` no longer overwrites `data/definitions.yml`.** It now writes a raw,
  un-patched snapshot of the upstream spreadsheet to
  `data/import/<YYYYMMDD_HHMMSS>.yml`. Diff two snapshots to spot upstream changes
  and hand-apply them to `data/modules/` — a transitional aid until the spreadsheet
  is retired.

### Removed

* **`data/patches/`** — the partial-overlay patch files are gone; each one's content
  is folded into the full `data/modules/*.yml` definition.


## 0.5.2 — 2026-06-25

API authentication for the compute-bound endpoints.

### Added

* **API key auth for `POST /api/v1/validate` and `POST /api/v1/solve`** (spec
  009). Machine consumers send `Authorization: Bearer <key>`; keys live in a YAML
  file (`WISMAP_API_KEYS_FILE`) and rotate via a server restart. The browser SPA
  authenticates transparently with a session + CSRF cookie pair — no key in the
  bundle. Discovery/read endpoints stay public. New env vars
  `WISMAP_AUTH_ENABLED`, `WISMAP_API_KEYS_FILE`, `WISMAP_SECRET_KEY`; when auth is
  enabled the server fails closed (refuses to start) if the secret or keys file
  is missing. Successful and denied auth events are logged (the matched consumer
  `label` on success, never the key); `WISMAP_LOG_LEVEL` (default `INFO`) tunes
  verbosity.

### API

* `openapi.yaml` documents `securitySchemes.bearerAuth` and a `403 Forbidden`
  response on `/validate` and `/solve` (additive — no breaking change within v1).


## 0.5.1 — 2026-06-23

Compact shareable combine links, a long-sensor data correction, and a
combine-tool deep-link fix.

### Data

* The `double` (long sensor) flag now matches the physical module set. Added to
  `RAK12500` and `RAK12501` (GNSS); removed from `RAK12001` (Fingerprint) and
  `RAK12059` (Liquid Level), which are single-slot. 

### Frontend

* Compact, versioned combine share links. The hash is now `#c/<v><tokens>`,
  encoding the base and each slot as a fixed-width hex code derived from its RAK
  number (empty/blocked slots zero-filled, trailing empties trimmed); a leading
  version digit lets the format evolve. Replaces the verbose
  `#combine/<base>/<mod>/…` form. The URL is kept in sync with the current layout
  via `history.replaceState`, so copying from the address bar always reflects the
  current selection without polluting browser history.

### Fixes

* Combine tool: a double sensor opened from a shared `#c/...` link now blocks its
  sibling slot on page load instead of only after the first manual edit. The
  deep-link apply effect ran before the module catalog finished loading, so
  `computeBlocked` couldn't see the `double` flag; it now defers applying the
  config until the catalog is available and re-runs when it arrives.


## 0.5.0 — 2026-06-19

Adds the slot solver — a placement endpoint that complements `/validate`.

### API

* New `POST /api/v1/solve` endpoint: given a `core` + `base` + a flat
  list of `modules`, returns up to `max_solutions` (default 3, clamped to 1–5)
  ranked slot placements — placements + scores only, **no pin map** (call
  `/validate` on the chosen layout for pins). Ranks by most-placed → fewest
  errors → fewest warnings → most sensors on the top layer → deterministic slot
  order; when not truncated, every returned layout is maximum-placement. Unknown,
  base-incompatible, and over-capacity modules are reported per solution in
  `unplaced[]`. Additive and non-breaking under the v1 contract.
* New per-slot `layer` (`top` | `bottom`) attribute on bases, surfaced in
  `GET /api/v1/bases/:id` as `slot_info[*].layer`. Drives the solver's top-layer
  ranking. `top` is the default; only bottom-face slots are annotated in the
  catalog patches.

### Tests

* Canonical `/api/v1/solve` fixtures under `tests/fixtures/solve/`.


## 0.4.0 — 2026-05-18

Major release: new consumer-facing API contract, frontend migrated, and a
formal OpenAPI document with an interactive Swagger UI.

### API

* New versioned JSON API under `/api/v1/*`, designed against the WisBlock
  Code Generator team's draft:
  - `GET /api/v1/healthz`
  - `GET /api/v1/cores` and `GET /api/v1/cores/:id`
  - `GET /api/v1/bases` and `GET /api/v1/bases/:id`
  - `GET /api/v1/modules` (filter by `type`, `category`, `interface`,
    `compatible_with_core`) and `GET /api/v1/modules/:id`
  - `POST /api/v1/validate` returns structured `conflicts[]` / `warnings[]`
    with `{code, severity, involves, context, hint}`, a `resolved` block
    that includes per-pin `role` / `wisblock_pin` / `mcu_pin`, plus a
    `buses` map and `lorawan` block
* Legacy non-versioned endpoints removed: `GET /api/modules`,
  `GET /api/modules/:id`, `GET /api/bases/:id/slots`, `POST /api/combine`.
  Frontend uses `/api/v1/*` exclusively.
* `/api/image-proxy` retained as an internal utility for the frontend's
  PDF-export flow (not part of the consumer contract).
* Coreless bases (e.g. RAK6421 Pi Hat): `core` is optional in
  `POST /api/v1/validate` when the base has no CORE slot; `resolved.core`
  and `resolved.lorawan` are `null` in that case.

### Documentation

* Canonical OpenAPI 3.1 doc at `wismap/openapi.yaml`, served verbatim at
  `GET /api/v1/openapi.yaml`.
* Interactive Swagger UI at `GET /api/v1/docs` (vendored static assets,
  CSP carve-out scoped to that path only).
* Test fixtures at `tests/fixtures/validate/` (15 canonical request/
  response pairs) for downstream-consumer CI; regeneratable via
  `python tests/fixtures/_generate.py`.
* `make check-openapi` drift check asserts every registered v1 route has
  a documented path and `info.version` matches `wismap.__version__`.

### Data enrichment

* All Cores now carry `mcu`, `lora_chip` (where applicable), and
  `power_pins.3V3_S_control`.
* All Bases carry `form_factor` (`mini | normal | large`) and
  `core_socket`.
* All non-Core/Base modules carry a `category`
  (`sensor | io | display | communication | storage | power`); 22 modules
  carry a concrete `chip` name (more populated incrementally).
* `rules.yml` gained `code` + `severity` per rule for structured conflict
  output.

### Frontend

* Migrated from the legacy `/api/*` to `/api/v1/*` exclusively.
* New unified browse view fetches Cores, Bases, and Modules in parallel.
* Module detail dispatches by type to the appropriate `/api/v1/*` endpoint.
* Combine tool derives slot eligibility from `module.compatible_slots` and
  `base.slot_info`; passes `core` at the top level per the spec contract.
* Conflict rendering uses structured `{code, severity, message, involves}`
  items; warnings styled distinctly from errors.

### Fixes

* Slot-names slicing in `_detect_conflicts` was off-by-one (latent because
  the legacy `exclude:` filter rarely fired); now corrected — `involves[]`
  in structured conflicts is populated correctly.
* Combine tool stale-state on base switch: `result` is cleared and the
  validate effect bails until `baseInfo.id === selectedBase`; a monotonic
  request id drops late responses from previous bases.


## 0.3.1 — 2026-03-14

* Add export options (PDF, Markdown) to the module detail page
* Improve PDF export layout
* CLI combine: validate input modules and skip empty slots in output


## 0.3.0 — 2026-02-27

* Add searchable tags to all ~140 modules (protocol, sensor type, communication, use case)
* Tags stored in patch files and merged into definitions.yml during import
* Web UI: search now matches against module tags in addition to ID and description
* Web UI: module detail page shows tags as clickable badges that filter the module list
* CLI: new `search` action to filter modules by type, description, or tags
* CLI: `info` action now displays tags
* CLI: `list` and `search` actions now include a Documentation column


## 0.2.1 — 2026-02-27

* Add version flag (`-v`/`--version`) to the CLI
* Show version in the web UI footer and in exported documents
* Preserve module list filters (type, search) when navigating to a module detail and back
* Add "Clear" button to reset active filters in the modules list
* Refactor WisCore module data to use pin numbers instead of names
* Rename the "mapping" key in definitions.yml for WisBase modules to "naming"


## 0.2.0 — 2026-02-16

First release with the web interface.

* REST API (Flask) serving module data, slot info, and combine analysis
* React 19 SPA (Vite) with module browser, detail view, and combine tool
* Export combine results to PDF or Markdown
* Shareable hash-based URLs for combine configurations (`#combine/base/mod1/...`)
* Docker multi-stage build and docker-compose support
* Split `patches.yml` into per-module files under `data/patches/`
* Combine view as default landing page
* Dynamic combine table updates as modules are selected
* Module images and schematics shown in detail view
* Keep page context when switching between Combine and Modules views
* Sort slots in canonical order across base boards
* Data cleanup: fix typos, inconsistencies, and documentation links


## 0.1.0 — 2024-07-29

Initial CLI-only release.

* List all WisBlock modules with type and description
* View detailed pin mappings and documentation for any module
* Combine modules on a base board and detect pin conflicts:
  - I2C address collisions
  - AIN0 / ADC_VBAT conflicts
  - Duplicate IO/AIN/GPIO/UART/LED/SW/SPI_CS usage
  - IO2 vs 3V3_S enable signal conflict
  - SPI chip-select conflicts
* Double-sensor slot blocking
* Import definitions from the official RAKwireless Pin Mapper spreadsheet
* Per-module patch files for custom overrides
* Support for ~140 modules across all WisBlock types (Base, Core, IO, Sensor, Power)
* Markdown table output (`-m`) and NC pin display (`-n`) options
* Pass module arguments directly on the command line (non-interactive mode)
* Reproduce configuration command printed after combine output
