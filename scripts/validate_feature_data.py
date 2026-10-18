"""Validate Erlan's additions without API requests, keys or changes to existing POIs."""
import argparse
import json
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import Field, ValidationError, create_model

from backend.config import ROOT
from backend.feature_data import FeatureData, MODELS
from backend.loader import load_pois
from backend.schemas import Model


def write_schemas(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for name, record in MODELS.items():
        envelope = create_model(record.__name__ + "File", __base__=Model,
                                version=(Literal[1], 1),
                                items=(list[record], Field(max_length=5000)))
        (directory / name.replace(".json", ".schema.json")).write_text(
            json.dumps(envelope.model_json_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--poi", type=Path, default=ROOT / "data/poi.json")
    parser.add_argument("--write-schemas", type=Path)
    args = parser.parse_args()
    if args.write_schemas:
        write_schemas(args.write_schemas)
    missing = [name for name in MODELS if not (args.data_dir / name).is_file()]
    if missing:
        print(json.dumps({"status": "invalid", "missing_files": missing}))
        return 1
    try:
        data = FeatureData(args.data_dir, load_pois(args.poi).pois)
    except (ValueError, OSError) as exc:
        # Print field paths and error types, not untrusted source text or private notes.
        errors = ([{"path": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
                  if isinstance(exc, ValidationError) else [{"type": str(exc).split(":", 1)[0][:100]}])
        print(json.dumps({"status": "invalid", "errors": errors}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "valid", "licensed_places": len(data.owned),
                      "comfort_points": len(data.comfort), "visit_conditions": len(data.conditions),
                      "atmosphere_examples": len(data.atmosphere),
                      "identity_aliases": len(data.identities), "fingerprint": data.fingerprint}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
