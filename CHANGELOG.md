Changelog
=========

All notable changes to this project will be documented in this file.


## Unreleased

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

* New `POST /api/v1/solve` endpoint (spec 010): given a `core` + `base` + a flat
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
  Code Generator team's draft and the negotiated review document
  (see `.sdd/specs/005-wismap-api-v1/`):
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
  carry a concrete `chip` name (more populated incrementally — see
  `.sdd/specs/007-power-data-backfill/`).
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
