from typing import Any

from .base import N8nTarget, build_workflow
from .v2_30 import TARGET as V2_30
from .v2_31 import TARGET as V2_31
from .v2_32 import TARGET as V2_32


TARGETS: dict[str, N8nTarget] = {
    V2_30.minor: V2_30,
    V2_31.minor: V2_31,
    V2_32.minor: V2_32,
}
SUPPORTED_TARGETS = tuple(reversed(TARGETS))


def export_n8n(process_ir: dict[str, Any], target_minor: str) -> dict[str, Any]:
    try:
        target = TARGETS[target_minor]
    except KeyError as error:
        supported = ", ".join(SUPPORTED_TARGETS)
        raise ValueError(f"Unsupported n8n target {target_minor}. Supported targets: {supported}.") from error
    return build_workflow(process_ir, target)
