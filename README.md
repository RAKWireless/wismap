WisMAP - WisBlock Pin Mapper
==========================

WisMAP identifies potential pin conflicts between modules in [RAKwireless WisBlock](https://www.rakwireless.com/en-us/products/wisblock) integrations. It is a port of the official [WisBlock Pin Mapper spreadsheet](https://downloads.rakwireless.com/LoRa/WisBlock/Pin-Mapper/WisBlock-IO-Pin-Mapper.xlsx) with a web interface and a CLI tool.

Features:

* Browse all WisBlock modules with filtering by type and category (filters persist across navigation)
* Search modules by name, description, or tags (protocol, sensor type, communication, use case)
* View detailed pin mappings, documentation links, and clickable tags for any module
* Combine modules on a base board and detect pin conflicts, I2C address collisions, and signal incompatibilities
* Export combine results to Markdown or PDF
* Shareable URLs for combine configurations
* Versioned JSON API (`/api/v1/*`) with interactive Swagger UI documentation at `/api/v1/docs`
* Supports ~140 modules across all WisBlock types (Base, Core, IO, Sensor, Power, Module, Accessories)

The REST API (Flask) and the web frontend (React) have been developed with the assistance of [Claude Code](https://claude.ai/code), Anthropic's AI coding tool.

## Deploy with Docker

The quickest way to run WisMAP is with Docker Compose:

```
git clone https://github.com/xoseperez/wismap
cd wismap
docker compose up -d --build
```

The web interface will be available at http://localhost:5000.

To stop the service:

```
docker compose down
```

Alternatively, using plain Docker:

```
docker build -t wismap .
docker run -p 5000:5000 wismap
```

## Deploy manually

Requirements: Python 3, Node.js, `virtualenv` and `make`.

```
git clone https://github.com/xoseperez/wismap
cd wismap
make init
make frontend-install
make frontend-build
make serve
```

This starts the Flask server on port 5000, serving both the API and the built frontend.

## Development

For local development, run the Flask API and the Vite dev server simultaneously in two terminals:

```
make serve
```

```
make frontend-dev
```

The Vite dev server proxies `/api` requests to Flask on port 5000 and provides hot module replacement.

## Updating module definitions

The repository includes a pre-built `data/definitions.yml` with ~140 module definitions. To update it from the latest official spreadsheet:

```
make import
```

This downloads the spreadsheet, parses each sheet, applies patches from `data/patches/*.yml`, and regenerates `definitions.yml`.

## CLI

WisMAP also provides a command-line interface for terminal usage. See [CLI.md](CLI.md) for full documentation.

Quick examples:

```
python wismap.py -v              # show version
python wismap.py list            # list all modules
python wismap.py search modbus   # search modules by tag, type, or description
python wismap.py info rak12008   # show module details
python wismap.py combine rak6421 rak5802 rak5801 empty empty rak12002 rak18001
```

## HTTP API

WisMAP exposes a versioned JSON API at `/api/v1/*`. The full contract is
machine-readable as OpenAPI 3.1:

* **Interactive browser**: http://localhost:5000/api/v1/docs (Swagger UI)
* **Raw OpenAPI document**: http://localhost:5000/api/v1/openapi.yaml

Endpoints:

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/healthz` | Liveness probe |
| `GET` | `/api/v1/cores` · `/cores/:id` | List / get a Core |
| `GET` | `/api/v1/bases` · `/bases/:id` | List / get a Base |
| `GET` | `/api/v1/modules` · `/modules/:id` | List / get a non-Core, non-Base module |
| `POST` | `/api/v1/validate` | Validate a `{core, base, slots[]}` configuration; returns structured conflicts and a resolved pin map |
| `POST` | `/api/v1/solve` | Solve which slot each requested module goes in; returns up to `max_solutions` ranked placements (no pin map — call `/validate` on the chosen one) |

Test fixtures — canonical request/response pairs for `/api/v1/validate` and
`/api/v1/solve` — live in `tests/fixtures/{validate,solve}/` for
downstream-consumer CI.

## Environment variables

The following environment variables can be used to configure the server:

| Variable | Default | Description |
|---|---|---|
| `FLASK_DEBUG` | `false` | Enable Flask debug mode (`true`, `1`, or `yes` to enable) |
| `RATELIMIT_ENABLED` | `true` | Enable API rate limiting (`false` to disable, e.g. during development) |
| `RATELIMIT_DEFAULT` | `120/minute` | Default rate limit for all API endpoints |
| `RATELIMIT_PROXY` | `60/minute` | Rate limit for `GET /api/image-proxy` |
| `RATELIMIT_STORAGE_URI` | `memory://` | Storage backend for rate limit counters (use `redis://host:6379` for multi-worker deployments) |

Rate limit values use the format `<amount>/<period>` where period is `second`, `minute`, `hour`, or `day`.

When running with Docker Compose, set these in a `.env` file or pass them directly:

```
docker compose up -d -e RATELIMIT_DEFAULT=240/minute
```

## Roadmap

* Suggest which module should go to which slot
* Add dependencies between modules (i.e. RAK14011 depends on RAK14004)

## Contribute

There are several ways to contribute to this project. You can [report](http://github.com/xoseperez/wismap/issues) bugs or [ask](http://github.com/xoseperez/wismap/issues) for new features directly on GitHub.
You can also submit your own new features of bug fixes via a [pull request](http://github.com/xoseperez/wismap/pr).

## License

This project is licensed under [Apache 2.0](http://www.apache.org/licenses/LICENSE-2.0) license.
