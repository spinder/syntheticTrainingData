#!/usr/bin/env python3
import argparse
import json
import sys
from pydantic import ValidationError
from schema.model import HomeDiyRepairQA

parser = argparse.ArgumentParser(description="Validate a JSON record against HomeDiyRepairQA schema")
parser.add_argument("file", help="Path to the JSON file to validate")
args = parser.parse_args()

try:
    with open(args.file) as f:
        data = json.load(f)
except FileNotFoundError:
    print(f"Error: file not found: {args.file}")
    sys.exit(2)
except json.JSONDecodeError as e:
    print(f"Error: invalid JSON in {args.file}: {e}")
    sys.exit(2)

try:
    obj = HomeDiyRepairQA.model_validate(data)
    print(f"VALID  {obj.id} | {obj.category}")
    sys.exit(0)
except ValidationError as e:
    print(f"INVALID  {args.file} — {e.error_count()} error(s):")
    for err in e.errors():
        field = ".".join(str(x) for x in err["loc"]) or "(root)"
        print(f"  [{field}] {err['msg']}")
    sys.exit(1)
