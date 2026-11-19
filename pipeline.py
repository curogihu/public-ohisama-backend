"""Offline demonstration pipeline. Only synthetic local input is supported."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
DATA_FILES = (
    "members.json", "content.tver.target.json", "content.youtube.target.json",
    "content.other.target.json", "content.last_checked_date.json", "demo.json",
)
CATEGORIES = {"tver", "youtube-movie", "youtube-shorts", "youtube-live", "audio", "column"}
MEMBER_FIELDS = {"id", "name", "en_name", "generation", "isActive"}
ITEM_FIELDS = {
    "id", "title", "category", "members", "url", "description", "publishDate", "expiresAt",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def timestamp(value: object) -> datetime:
    require(isinstance(value, str), "Timestamp must be a string")
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None, "Timestamp must include a timezone")
    return result


def text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def build_payloads(raw: dict) -> tuple[dict[str, object], dict[str, int]]:
    """Validate all records before writing; collapse identical duplicates only."""
    require(isinstance(raw, dict), "Input must be an object")
    require(set(raw) == {"schemaVersion", "fictional", "referenceTime", "members", "content"}, "Unexpected input fields")
    require(raw["schemaVersion"] == 1 and raw["fictional"] is True, "Synthetic schema version 1 required")
    reference = timestamp(raw["referenceTime"])
    require(isinstance(raw["members"], list) and bool(raw["members"]), "Members must be a nonempty array")
    members, member_ids = [], set()
    for member in raw["members"]:
        require(isinstance(member, dict) and set(member) == MEMBER_FIELDS, "Unexpected member fields")
        require(text(member["id"]) and re.fullmatch(r"sample-[a-z0-9-]+", member["id"]) is not None, "Sample member ID required")
        require(member["id"] not in member_ids, "Duplicate member ID")
        require(text(member["name"]) and text(member["en_name"]), "Member names required")
        require(type(member["generation"]) is int and member["generation"] > 0, "Invalid generation")
        require(type(member["isActive"]) is bool, "Invalid member status")
        members.append({**member, "profileImage": "/placeholder.svg", "birthDate": "2000-01-01", "bloodType": "-", "height": "-", "hometown": "サンプル県"})
        member_ids.add(member["id"])

    require(isinstance(raw["content"], list), "Content must be an array")
    seen: dict[str, dict] = {}
    duplicates = 0
    for item in raw["content"]:
        require(isinstance(item, dict) and set(item) == ITEM_FIELDS, "Unexpected content fields")
        require(text(item["id"]) and re.fullmatch(r"demo-[a-z0-9-]+", item["id"]) is not None, "Demo content ID required")
        require(all(text(item[key]) for key in ("title", "description", "publishDate")), "Content text required")
        require(isinstance(item["category"], str) and item["category"] in CATEGORIES, "Unknown category")
        require(isinstance(item["members"], list) and bool(item["members"]), "Content members required")
        require(all(isinstance(value, str) and value in member_ids for value in item["members"]), "Unknown member reference")
        require(text(item["url"]), "Content URL required")
        url = urlsplit(item["url"])
        require(url.scheme == "https" and url.netloc == "example.com" and not url.username, "Only synthetic example.com URLs are allowed")
        require(re.fullmatch(r"\d{4}/\d{2}/\d{2}", item["publishDate"]) is not None, "Use YYYY/MM/DD")
        datetime.strptime(item["publishDate"], "%Y/%m/%d")
        if item["expiresAt"] is not None:
            timestamp(item["expiresAt"])
        if item["id"] in seen:
            require(seen[item["id"]] == item, "Conflicting duplicate content ID")
            duplicates += 1
        else:
            seen[item["id"]] = item

    grouped: dict[str, list] = {"tver": [], "youtube": [], "other": []}
    for item in sorted(seen.values(), key=lambda entry: entry["id"]):
        category = item["category"]
        group = "youtube" if category.startswith("youtube-") else "tver" if category == "tver" else "other"
        grouped[group].append({
            "id": item["id"], "title": item["title"],
            "type": "audio" if category == "audio" else "column" if category == "column" else "movie",
            "members": sorted(set(item["members"]) | {category}),
            "url": item["url"], "platform": "Radiko（架空）" if category == "audio" else {"tver": "TVer（架空）", "youtube": "YouTube（架空）", "other": "サンプル配信"}[group],
            "description": item["description"], "thumbnail": "/placeholder.svg",
            "publishDate": item["publishDate"], "expiresAt": item["expiresAt"],
        })
    payloads: dict[str, object] = {"members.json": members}
    for group in grouped:
        payloads[f"content.{group}.target.json"] = {"updated": reference.strftime("%Y/%m/%d"), "content": grouped[group]}
    payloads["content.last_checked_date.json"] = {"updated": reference.isoformat()}
    payloads["demo.json"] = {"schemaVersion": 1, "fictional": True, "referenceTime": reference.isoformat(), "expiryWindowDays": 7}
    return payloads, {"input": len(raw["content"]), "output": len(seen), "duplicates": duplicates}


def run(input_path: Path, output: Path) -> dict[str, int]:
    payloads, stats = build_payloads(json.loads(input_path.read_text(encoding="utf-8")))
    # Never overwrite an existing, unrelated JSON file or a linked destination.
    output = output.absolute()
    require(all(not path.is_symlink() for path in (output, *output.parents)), "Output must not traverse symbolic links")
    for name in DATA_FILES:
        target = output / name
        require(not target.is_symlink(), "Output files must not be symbolic links")
        if target.exists():
            existing = json.loads(target.read_text(encoding="utf-8"))
            if name == "demo.json":
                require(isinstance(existing, dict) and existing.get("fictional") is True, "Refusing to replace non-demo output")
    if output.exists() and any((output / name).exists() for name in DATA_FILES):
        marker = output / "demo.json"
        require(marker.exists() and json.loads(marker.read_text(encoding="utf-8")).get("fictional") is True, "Existing output needs a fictional demo marker")
    output.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        (output / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "samples/input.json")
    parser.add_argument("--output", type=Path, default=ROOT / "output")
    args = parser.parse_args()
    try:
        stats = run(args.input, args.output)
    except (ValueError, OSError, TypeError, KeyError) as error:
        # Do not print source records or potentially sensitive parser error values.
        print(f"Batch failed ({type(error).__name__}); input/output validation failed.", file=sys.stderr)
        return 1
    print(json.dumps(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
