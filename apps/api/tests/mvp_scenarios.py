import json
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class MvpScenario:
    id: str
    entry_mode: str
    fixture_name: str

    def load_process_ir(self) -> dict:
        path = ROOT / "02_architecture" / "examples" / self.fixture_name
        return json.loads(path.read_text(encoding="utf-8"))


MVP_SCENARIOS = (
    MvpScenario("ready_template", "ready_template", "lead-intake.process-ir.json"),
    MvpScenario("interview_template", "interview_template", "invoice-approval.process-ir.json"),
    MvpScenario("dialogue_only", "dialogue_only", "support-ticket.process-ir.json"),
)
