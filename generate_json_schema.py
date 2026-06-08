import json

from schema.model import HomeDiyRepairQA

schema = HomeDiyRepairQA.model_json_schema()

schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
schema["title"] = "HomeDiyRepairQA"

with open("schema/home_diy_repair_qa.schema.json", "w") as f:
    json.dump(schema, f, indent=2)
print("Schema generated: schema/home_diy_repair_qa.schema.json")
