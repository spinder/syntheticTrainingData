# syntheticTrainingData
A training project.

##Setup
# Install the dependencies
pip install datasets huggingface_hub pydantic jsonschema pandas pyarrow

# Generate the schema
python generate_json_schema.py
python validate_schema_self_check.py
## NOTE: to run validation you will need to add HF api key.
#python validate_hf_dataset.py

