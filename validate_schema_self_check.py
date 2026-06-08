import json
from jsonschema import Draft202012Validator

with open("schema/home_diy_repair_qa.schema.json", "r") as f:
    schema = json.load(f)

Draft202012Validator.check_schema(schema)

valid_example = {
    "question": "How do I fix a leaking sink drain?",
    "answer": "Turn off the water supply valve under the sink, place a bucket to catch drips, loosen the drain nut with slip-joint pliers, pull out the drain assembly, replace the worn washer or gasket, and reassemble. Test by running water.",
    "equipment_problem": "Leaking sink drain",
    "tools_required": ["bucket", "slip-joint pliers", "replacement washer or gasket"],
    "steps": ["Turn off the supply valve under the sink", "Loosen the drain nut with pliers", "Replace the worn washer or gasket"],
    "safety_info": "Turn the supply valve fully off before disassembly — residual pressure will spray water if the drain nut is loosened with flow still present.",
    "tips": ["Take a photo of the drain assembly before disassembly so you know the correct reassembly order."]
}

validator = Draft202012Validator(schema)
errors = list(validator.iter_errors(valid_example))

if errors:
    print("Example failed validation:")
    for error in errors:
        print(error.message)
else:
    print("Schema is valid and example row passed.")
