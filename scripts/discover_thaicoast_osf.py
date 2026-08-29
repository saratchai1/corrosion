#!/usr/bin/env python3
"""Inventory the public ThaiCoast OSF project and its components.

The published CoastSat/DSAS study states that its GIS files are available at
https://osf.io/mxjhk/.  This script walks the OSF API anonymously, records every
public file and component, and highlights GIS/shoreline/DSAS/Krabi candidates.
It deliberately does not guess file paths or silently skip pagination.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

API = "https://api.osf.io/v2"
ROOT_NODE = "mxjhk"
USER_AGENT = "corrosion-thaicoast-osf-inventory/1.0"
KEYWORDS = re.compile(
    r"(krabi|กระบี่|shore|coast|dsas|transect|lrr|epr|nsm|gis|shape|shp|geojson|geopackage|gpkg|kml|kmz|zip|rar|7z)",
    re.IGNORECASE,
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_json(session: requests.Session, url: str) -> dict[str, Any]:
    response = session.get(url, timeout=120)
    response.raise_for_status()
    return response.json()


def iter_collection(session: requests.Session, url: str):
    next_url: str | None = url
    seen: set[str] = set()
    while next_url:
        if next_url in seen:
            raise RuntimeError(f"Pagination loop detected: {next_url}")
        seen.add(next_url)
        payload = get_json(session, next_url)
        yield from payload.get("data", [])
        next_url = payload.get("links", {}).get("next")


def compact_node(item: dict[str, Any]) -> dict[str, Any]:
    attrs = item.get("attributes", {})
    links = item.get("links", {})
    return {
        "id": item.get("id"),
        "title": attrs.get("title"),
        "category": attrs.get("category"),
        "description": attrs.get("description"),
        "public": attrs.get("public"),
        "date_created": attrs.get("date_created"),
        "date_modified": attrs.get("date_modified"),
        "html": links.get("html"),
    }


def compact_file(item: dict[str, Any], node_id: str, node_title: str) -> dict[str, Any]:
    attrs = item.get("attributes", {})
    links = item.get("links", {})
    extra = attrs.get("extra") or {}
    hashes = extra.get("hashes") or {}
    materialized = attrs.get("materialized_path") or attrs.get("name") or ""
    return {
        "node_id": node_id,
        "node_title": node_title,
        "id": item.get("id"),
        "name": attrs.get("name"),
        "kind": attrs.get("kind"),
        "path": attrs.get("path"),
        "materialized_path": materialized,
        "size": attrs.get("size"),
        "provider": attrs.get("provider"),
        "date_created": attrs.get("date_created"),
        "date_modified": attrs.get("date_modified"),
        "md5": hashes.get("md5"),
        "sha256": hashes.get("sha256"),
        "download": links.get("download"),
        "html": links.get("html"),
        "move": links.get("move"),
        "matches_keywords": bool(KEYWORDS.search(materialized)),
    }


def related_href(item: dict[str, Any], relationship: str) -> str | None:
    rel = item.get("relationships", {}).get(relationship, {})
    related = rel.get("links", {}).get("related")
    if isinstance(related, dict):
        return related.get("href")
    if isinstance(related, str):
        return related
    return None


def walk_file_collection(
    session: requests.Session,
    url: str,
    node_id: str,
    node_title: str,
    output: list[dict[str, Any]],
) -> None:
    for item in iter_collection(session, url):
        entry = compact_file(item, node_id, node_title)
        output.append(entry)
        if entry["kind"] == "folder":
            children_url = related_href(item, "files")
            if not children_url:
                # OSF folder metadata usually exposes links.move as a directory URL.
                move = entry.get("move")
                if move:
                    children_url = move
            if children_url:
                walk_file_collection(session, children_url, node_id, node_title, output)


def list_node_files(session: requests.Session, node: dict[str, Any]) -> list[dict[str, Any]]:
    node_id = str(node["id"])
    title = node.get("title") or node_id
    output: list[dict[str, Any]] = []
    providers_url = f"{API}/nodes/{node_id}/files/"
    for provider in iter_collection(session, providers_url):
        files_url = provider.get("links", {}).get("files")
        if files_url:
            walk_file_collection(session, files_url, node_id, title, output)
    return output


def discover_nodes(session: requests.Session) -> list[dict[str, Any]]:
    root_raw = get_json(session, f"{API}/nodes/{ROOT_NODE}/")["data"]
    nodes = [compact_node(root_raw)]
    queue = [root_raw]
    seen = {ROOT_NODE}
    while queue:
        parent = queue.pop(0)
        parent_id = parent.get("id")
        children_url = related_href(parent, "children") or f"{API}/nodes/{parent_id}/children/"
        for child_raw in iter_collection(session, children_url):
            child_id = str(child_raw.get("id"))
            if not child_id or child_id in seen:
                continue
            seen.add(child_id)
            nodes.append(compact_node(child_raw))
            queue.append(child_raw)
    return nodes


def human_size(value: int | None) -> str:
    if value is None:
        return "unknown"
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.2f} {unit}"
        size /= 1024
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("regions/krabi/data/published/thaicoast_osf_inventory.json"),
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("regions/krabi/data/published/thaicoast_osf_inventory.md"),
    )
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.api+json, application/json",
        }
    )

    nodes = discover_nodes(session)
    files: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for node in nodes:
        try:
            files.extend(list_node_files(session, node))
        except Exception as exc:  # inventory should expose partial failures explicitly
            errors.append({"node_id": str(node.get("id")), "error": str(exc)})

    candidates = [entry for entry in files if entry.get("matches_keywords")]
    payload = {
        "generated_utc": now_utc(),
        "source_project": f"https://osf.io/{ROOT_NODE}/",
        "api_root": API,
        "root_node": ROOT_NODE,
        "node_count": len(nodes),
        "file_count": len(files),
        "candidate_count": len(candidates),
        "total_file_bytes": sum(int(item.get("size") or 0) for item in files if item.get("kind") == "file"),
        "nodes": nodes,
        "files": sorted(files, key=lambda x: (x.get("node_title") or "", x.get("materialized_path") or "")),
        "candidates": sorted(candidates, key=lambda x: (x.get("node_title") or "", x.get("materialized_path") or "")),
        "errors": errors,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# ThaiCoast OSF inventory",
        "",
        f"- Generated: `{payload['generated_utc']}`",
        f"- Source: `{payload['source_project']}`",
        f"- Nodes/components: **{len(nodes)}**",
        f"- Files/folders: **{len(files)}**",
        f"- Keyword candidates: **{len(candidates)}**",
        f"- Total file bytes: **{human_size(payload['total_file_bytes'])}**",
        f"- Partial errors: **{len(errors)}**",
        "",
        "## Candidate files",
        "",
        "| Component | Path | Kind | Size | Download |",
        "|---|---|---:|---:|---|",
    ]
    for item in candidates:
        path = str(item.get("materialized_path") or item.get("name") or "").replace("|", "\\|")
        title = str(item.get("node_title") or item.get("node_id") or "").replace("|", "\\|")
        download = item.get("download") or ""
        lines.append(
            f"| {title} | `{path}` | {item.get('kind')} | {human_size(item.get('size'))} | {download} |"
        )
    if errors:
        lines.extend(["", "## Errors", ""])
        for error in errors:
            lines.append(f"- `{error['node_id']}`: {error['error']}")
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "node_count": len(nodes),
                "file_count": len(files),
                "candidate_count": len(candidates),
                "total_file_bytes": payload["total_file_bytes"],
                "errors": errors,
                "out": str(args.out),
                "summary": str(args.summary),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
