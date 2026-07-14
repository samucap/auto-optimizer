"""Dynamic JSON Schema validation (schema provided by agents, not hard-coded)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(instance: Any, schema: dict[str, Any]) -> list[str]:
    try:
        import jsonschema
        from jsonschema import Draft202012Validator
    except ImportError:
        # Minimal fallback: type + required only
        return _minimal_validate(instance, schema)

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors]


def _minimal_validate(instance: Any, schema: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    t = schema.get("type")
    if t == "object" and not isinstance(instance, dict):
        errs.append(f"<root>: expected object, got {type(instance).__name__}")
        return errs
    if t == "array" and not isinstance(instance, list):
        errs.append(f"<root>: expected array, got {type(instance).__name__}")
        return errs
    if isinstance(instance, dict):
        for key in schema.get("required") or []:
            if key not in instance:
                errs.append(f"missing required property: {key}")
    return errs


def validate_files(output_path: Path, schema_path: Path) -> list[str]:
    if not output_path.exists():
        return [f"output missing: {output_path}"]
    if not schema_path.exists():
        return [f"schema missing: {schema_path}"]
    try:
        instance = load_json(output_path)
    except json.JSONDecodeError as e:
        return [f"output JSON invalid: {e}"]
    try:
        schema = load_json(schema_path)
    except json.JSONDecodeError as e:
        return [f"schema JSON invalid: {e}"]
    if not isinstance(schema, dict):
        return ["schema must be a JSON object"]
    return validate(instance, schema)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate output.json against schema.json")
    ap.add_argument("output", type=Path)
    ap.add_argument("schema", type=Path)
    args = ap.parse_args(argv)
    errs = validate_files(args.output, args.schema)
    if errs:
        for e in errs:
            print(e, file=sys.stderr)
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
