#!/usr/bin/env python3
"""Inventory the public ThaiCoast OSF project, components, and registrations.

The published CoastSat/DSAS study states that its GIS files are available at
https://osf.io/mxjhk/. This script walks the OSF API anonymously, records every
public file, and highlights GIS/shoreline/DSAS/Krabi candidates. It resolves
provider endpoints directly instead of depending on one historical response
shape, and it also checks registrations linked to the project.
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
USER_AGENT = "corrosion-thaicoast-osf-inventory/1.1"
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


def related_href(item: dict[str, Any], relationship: str) -> str | None:
    rel = item.get("relationships", {}).get(relationship, {})
    related = rel.get("links", {}).get("related")
    if isinstance(related, dict):
        return related.get("href")
    if isinstance(related, str):
        return related
    return None


def compact_resource(item: dict[str, Any], resource_type: str) -> dict[str, Any]:
    attrs = item.get("attributes", {})
    links = item.get("links", {})
    return {
        "id": item.get("id"),
        "resource_type": resource_type,
        "title": attrs.get("title"),
        "category": attrs.get("category"),
        "description": attrs.get("description"),
        "public": attrs.get("public"),
        "date_created": attrs.get("date_created"),
        "date_modified": attrs.get("date_modified"),
        "html": links.get("html"),
    }


def compact_file(
    item: dict[str, Any],
    resource_id: str,
    resource_title: str,
    resource_type: str,
    provider_id: str,
) -> dict[str, Any]:
    attrs = item.get("attributes", {})
    links = item.get("links", {})
    extra = attrs.get("extra") or {}
    hashes = extra.get("hashes") or {}
    materialized = attrs.get("materialized_path") or attrs.get("name") or ""
    return {
        "resource_id": resource_id,
        "resource_title": resource_title,
        "resource_type": resource_type,
        "provider_id": provider_id,
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
        "matches_keywords": bool(KEYWORDS.search(materialized)),
    }


def walk_file_collection(
    session: requests.Session,
    url: str,
    resource: dict[str, Any],
    provider_id: str,
    output: list[dict[str, Any]],
    visited_folders: set[str],
) -> None:
    for item in iter_collection(session, url):
        entry = compact_file(
            item,
            str(resource["id"]),
            str(resource.get("title") or resource["id"]),
            str(resource["resource_type"]),
            provider_id,
        )
        output.append(entry)
        if entry["kind"] != "folder":
            continue
        folder_id = str(entry.get("id") or entry.get("path") or "")
        if folder_id in visited_folders:
            continue
        visited_folders.add(folder_id)
        children_url = related_href(item, "files")
        if children_url:
            walk_file_collection(
                session,
                children_url,
                resource,
                provider_id,
                output,
                visited_folders,
            )


def list_resource_files(
    session: requests.Session,
    resource: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    resource_id = str(resource["id"])
    resource_type = str(resource["resource_type"])
    collection = "nodes" if resource_type == "node" else "registrations"
    providers_url = f"{API}/{collection}/{resource_id}/files/"
    output: list[dict[str, Any]] = []
    providers: list[dict[str, Any]] = []
    for provider in iter_collection(session, providers_url):
        provider_id = str(provider.get("id") or "")
        attrs = provider.get("attributes", {})
        links = provider.get("links", {})
        providers.append(
            {
                "resource_id": resource_id,
                "resource_type": resource_type,
                "id": provider_id,
                "name": attrs.get("name"),
                "default": attrs.get("default"),
                "files_link": links.get("files"),
                "relationship_files": related_href(provider, "files"),
            }
        )
        files_url = (
            links.get("files")
            or related_href(provider, "files")
            or f"{API}/{collection}/{resource_id}/files/{provider_id}/"
        )
        try:
            walk_file_collection(
                session,
                files_url,
                resource,
                provider_id,
                output,
                set(),
            )
        except requests.HTTPError as exc:
            # Some unconfigured add-ons return 4xx. Keep provider metadata and
            # continue; the caller records the provider-level error explicitly.
            providers[-1]["files_error"] = str(exc)
    return output, providers


def discover_resources(session: requests.Session) -> list[dict[str, Any]]:
    root_raw = get_json(session, f"{API}/nodes/{ROOT_NODE}/")["data"]
    resources = [compact_resource(root_raw, "node")]
    queue = [root_raw]
    seen_nodes = {ROOT_NODE}
    seen_registrations: set[str] = set()
    while queue:
        parent = queue.pop(0)
        parent_id = str(parent.get("id"))
        children_url = related_href(parent, "children") or f"{API}/nodes/{parent_id}/children/"
        for child_raw in iter_collection(session, children_url):
            child_id = str(child_raw.get("id"))
            if not child_id or child_id in seen_nodes:
                continue
            seen_nodes.add(child_id)
            resources.append(compact_resource(child_raw, "node"))
            queue.append(child_raw)
        registrations_url = f"{API}/nodes/{parent_id}/registrations/"
        try:
            for reg_raw in iter_collection(session, registrations_url):
                reg_id = str(reg_raw.get("id"))
                if not reg_id or reg_id in seen_registrations:
                    continue
                seen_registrations.add(reg_id)
                resources.append(compact_resource(reg_raw, "registration"))
        except requests.HTTPError:
            pass
    return resources


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

    resources = discover_resources(session)
    files: list[dict[str, Any]] = []
    providers: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for resource in resources:
        try:
            resource_files, resource_providers = list_resource_files(session, resource)
            files.extend(resource_files)
            providers.extend(resource_providers)
        except Exception as exc:
            errors.append(
                {
                    "resource_id": str(resource.get("id")),
                    "resource_type": str(resource.get("resource_type")),
                    "error": str(exc),
                }
            )

    candidates = [entry for entry in files if entry.get("matches_keywords")]
    payload = {
        "generated_utc": now_utc(),
        "source_project": f"https://osf.io/{ROOT_NODE}/",
        "api_root": API,
        "root_node": ROOT_NODE,
        "resource_count": len(resources),
        "file_count": len(files),
        "candidate_count": len(candidates),
        "total_file_bytes": sum(
            int(item.get("size") or 0) for item in files if item.get("kind") == "file"
        ),
        "resources": resources,
        "providers": providers,
        "files": sorted(
            files,
            key=lambda x: (
                x.get("resource_title") or "",
                x.get("provider_id") or "",
                x.get("materialized_path") or "",
            ),
        ),
        "candidates": sorted(
            candidates,
            key=lambda x: (
                x.get("resource_title") or "",
                x.get("materialized_path") or "",
            ),
        ),
        "errors": errors,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# ThaiCoast OSF inventory",
        "",
        f"- Generated: `{payload['generated_utc']}`",
        f"- Source: `{payload['source_project']}`",
        f"- Resources (nodes + registrations): **{len(resources)}**",
        f"- Storage providers: **{len(providers)}**",
        f"- Files/folders: **{len(files)}**",
        f"- Keyword candidates: **{len(candidates)}**",
        f"- Total file bytes: **{human_size(payload['total_file_bytes'])}**",
        f"- Partial errors: **{len(errors)}**",
        "",
        "## Storage providers",
        "",
        "| Resource | Type | Provider | Files error |",
        "|---|---|---|---|",
    ]
    for provider in providers:
        lines.append(
            "| {resource_id} | {resource_type} | {provider} | {error} |".format(
                resource_id=provider.get("resource_id"),
                resource_type=provider.get("resource_type"),
                provider=provider.get("id"),
                error=str(provider.get("files_error") or "").replace("|", "\\|"),
            )
        )
    lines.extend(
        [
            "",
            "## Candidate files",
            "",
            "| Resource | Path | Kind | Size | Download |",
            "|---|---|---:|---:|---|",
        ]
    )
    for item in candidates:
        path = str(item.get("materialized_path") or item.get("name") or "").replace("|", "\\|")
        title = str(item.get("resource_title") or item.get("resource_id") or "").replace("|", "\\|")
        download = item.get("download") or ""
        lines.append(
            f"| {title} | `{path}` | {item.get('kind')} | {human_size(item.get('size'))} | {download} |"
        )
    if errors:
        lines.extend(["", "## Errors", ""])
        for error in errors:
            lines.append(
                f"- `{error['resource_type']}:{error['resource_id']}`: {error['error']}"
            )
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "resource_count": len(resources),
                "provider_count": len(providers),
                "file_count": len(files),
                "candidate_count": len(candidates),
                "total_file_bytes": payload["total_file_bytes"],
                "errors": errors,
                "providers": providers,
                "candidate_paths": [
                    item.get("materialized_path") for item in candidates[:50]
                ],
                "out": str(args.out),
                "summary": str(args.summary),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
