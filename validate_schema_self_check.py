import json
from jsonschema import Draft202012Validator

with open("home_diy_repair_qa.schema.json", "r") as f:
    schema = json.load(f)

Draft202012Validator.check_schema(schema)

valid_example = {
    "id": "qa_999",
    "category": "plumbing_repair",
    "question": "How do I fix a leaking sink drain?",
    "answer": "Turn off the water, inspect the drain assembly, replace worn washers or plumber's putty, and test carefully.",
    "issue": "Leaking sink drain",
    "tools": ["bucket", "adjustable wrench", "plumber's putty"],
    "steps": ["Place bucket under sink", "Loosen drain nut", "Replace seal", "Retighten and test"],
    "safety_notes": "Avoid over-tightening fittings and clean up water immediately.",
    "tips": ["Take a photo before disassembly"]
}

validator = Draft202012Validator(schema)
errors = list(validator.iter_errors(valid_example))

if errors:
    print("Example failed validation:")
    for error in errors:
        print(error.message)
else:
    print("Schema is valid and example row passed.")
