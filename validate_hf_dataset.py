from datasets import load_dataset
from pydantic import ValidationError
from schema.model import HomeDiyRepairQA

dataset = load_dataset("dipenbhuva/home-diy-repair-qa", split="train")

print("Columns:", dataset.column_names)
print("Rows:", len(dataset))
print("First row:", dataset[0])

bad_rows = []

for index, row in enumerate(dataset):
    try:
        HomeDiyRepairQA.model_validate(row)
    except ValidationError as error:
        bad_rows.append({
            "index": index,
            "id": row.get("id"),
            "errors": error.errors()
        })

print("Validation complete.")
print("Valid rows:", len(dataset) - len(bad_rows))
print("Bad rows:", len(bad_rows))

if bad_rows:
    print("First bad row:")
    print(bad_rows[0])
