#!/bin/bash
python -m jsonschema --instance tests/row.json schema/home_diy_repair_qa.schema.json
python -m jsonschema --instance tests/bad_row.json schema/home_diy_repair_qa.schema.json
