"""Writes a static snapshot of the OpenAPI spec to dist-openapi/openapi.json.

There is no live deployment of this API to browse /docs on — `main.py` sets
docs_url/redoc_url/openapi_url to None whenever APP_ENV is production (see
main.py, IS_PRODUCTION). This script never touches that: it imports the
FastAPI `app` object directly and calls `app.openapi()`, which builds the
schema dict from the route/Pydantic metadata in-process, independent of
whether the docs routes are mounted. No HTTP server is started, and no
database is required — SQLAlchemy's create_engine() (database.py) is lazy
and never connects during import.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import app  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "dist-openapi" / "openapi.json"


def main() -> None:
    schema = app.openapi()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(schema))
    print(f"OpenAPI spec written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
