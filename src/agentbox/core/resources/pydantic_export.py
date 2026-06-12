"""Render a JSON Schema as Pydantic v2 model source code.

Uses ``datamodel-code-generator`` under the hood. Kept as a thin wrapper
so the API route doesn't need to know about temp dirs or DCG flags.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from datamodel_code_generator import InputFileType, generate
from datamodel_code_generator.enums import DataModelType
from datamodel_code_generator.format import Formatter


def schema_to_pydantic(schema_json: str, class_name: str = "Model") -> str:
    """Generate Pydantic v2 model code from a JSON Schema string."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "model.py"
        generate(
            input_=schema_json,
            input_file_type=InputFileType.JsonSchema,
            output=out,
            output_model_type=DataModelType.PydanticV2BaseModel,
            class_name=class_name,
            use_schema_description=True,
            use_field_description=True,
            use_standard_collections=True,
            use_union_operator=True,
            target_python_version="3.12",  # type: ignore[arg-type]
            formatters=[Formatter.BLACK, Formatter.ISORT],
        )
        return out.read_text(encoding="utf-8")
