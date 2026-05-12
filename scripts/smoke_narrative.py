#!/usr/bin/env python3
"""Smoke-test the cypherclaw narrative API endpoints.

Reachable from either the cypherclaw machine (via localhost) or the Deniable
operator's Mac after a Tailscale connection. Stdlib-only so it can be copied
out without a virtualenv.

Usage:
    NARRATIVE_BASE_URL=http://cypherclaw:8765 python3 scripts/smoke_narrative.py
    python3 scripts/smoke_narrative.py --base-url http://100.x.y.z:8765 --token <secret>

The --token value is sent as ``X-Narrative-Auth`` and as an
``Authorization: Bearer <token>`` compatibility header.

Exit code: 0 if every endpoint returns 2xx, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, NamedTuple

DEFAULT_BASE_URL = "http://cypherclaw:8765"
BODY_PREVIEW_CHARS = 200
REQUEST_TIMEOUT_SECONDS = 1.0


class SmokeResult(NamedTuple):
    method: str
    path: str
    status_code: int | None
    body: str = ""
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status_code is not None and 200 <= self.status_code < 300


def request_endpoint(
    base_url: str,
    method: str,
    path: str,
    token: str | None,
    *,
    payload: dict[str, Any] | None = None,
    verbose: bool = False,
) -> SmokeResult:
    url = base_url.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    if token:
        request.add_header("X-Narrative-Auth", token)
        request.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(  # noqa: S310 - operator-supplied URL
            request, timeout=REQUEST_TIMEOUT_SECONDS
        ) as response:
            status_code = response.getcode()
            body = response.read()
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        body = exc.read() if exc.fp is not None else b""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"{method} {path} -> ERROR {exc}")
        return SmokeResult(method=method, path=path, status_code=None, error=str(exc))

    body_text = body.decode("utf-8", errors="replace")
    line = f"{method} {path} -> {status_code}"
    if verbose and body_text:
        preview = body_text[:BODY_PREVIEW_CHARS]
        if len(body_text) > BODY_PREVIEW_CHARS:
            preview += "..."
        one_line_preview = preview.replace("\n", r"\n")
        line += f" body={one_line_preview}"
    print(line)
    return SmokeResult(method=method, path=path, status_code=status_code, body=body_text)


def first_entity_id(body: str) -> str | None:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None
    entities = data.get("entities")
    if not isinstance(entities, list) or not entities:
        return None
    first_entity = entities[0]
    if not isinstance(first_entity, dict):
        return None
    entity_id = first_entity.get("id")
    return entity_id if isinstance(entity_id, str) and entity_id else None


def entity_get_path(entity_id: str) -> str:
    quoted_id = urllib.parse.quote(entity_id, safe="")
    return f"/world/entities/{quoted_id}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("NARRATIVE_BASE_URL", DEFAULT_BASE_URL),
        help="Narrative API base URL (env: NARRATIVE_BASE_URL).",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Optional token sent as X-Narrative-Auth and Authorization.",
    )
    parser.add_argument(
        "--entity-id",
        default=os.environ.get("NARRATIVE_ENTITY_ID"),
        help=(
            "Optional known-safe entity ID for GET /world/entities/{entity_id} "
            "(env: NARRATIVE_ENTITY_ID). Defaults to the first listed entity."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Also print the first 200 chars of each response body.",
    )
    args = parser.parse_args(argv)

    print(f"smoke_narrative: base_url={args.base_url}")
    ok = True

    def run(
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> SmokeResult:
        result = request_endpoint(
            args.base_url,
            method,
            path,
            args.token,
            payload=payload,
            verbose=args.verbose,
        )
        nonlocal ok
        if not result.ok:
            ok = False
        return result

    run("GET", "/health")
    run(
        "POST",
        "/memory/search",
        {"query": "smoke", "k": 1, "domain_filter": "shared"},
    )
    run("POST", "/beats/next", {"cycle_number": 0, "domain_filter": "shared"})
    entities = run("GET", "/world/entities?limit=1")
    entity_id = args.entity_id or first_entity_id(entities.body)
    if entity_id:
        run("GET", entity_get_path(entity_id))
    else:
        print("GET /world/entities/{entity_id} -> SKIP no entity id returned")
    run("GET", "/events?limit=1")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
