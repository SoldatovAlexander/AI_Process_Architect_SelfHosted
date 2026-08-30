import os
from pathlib import Path


WORKSPACE_ROOT = Path(
    os.environ.get("PROCESS_ARCHITECT_WORKSPACE_ROOT", Path(__file__).resolve().parents[4])
).resolve()
PROCESS_IR_SCHEMA_PATH = (
    WORKSPACE_ROOT / "02_architecture" / "schemas" / "process-ir.schema.json"
)
