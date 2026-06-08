from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Literal

Category = Literal[
    "appliance_repair",
    "general_home_repair",
    "plumbing_repair",
    "electrical_repair",
    "hvac_maintenance",
]

class HomeDiyRepairQA(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^qa_\d+$")
    category: Category
    question: str = Field(min_length=10, max_length=500)
    answer: str = Field(min_length=20, max_length=5000)
    issue: str = Field(min_length=5, max_length=300)
    tools: list[str] = Field(min_length=1, max_length=20)
    steps: list[str] = Field(min_length=1, max_length=25)
    safety_notes: str = Field(min_length=5, max_length=1000)
    tips: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("tools", "steps", "tips")
    @classmethod
    def no_empty_items(cls, values):
        for value in values:
            if not value.strip():
                raise ValueError("List fields cannot contain empty strings")
        return values
