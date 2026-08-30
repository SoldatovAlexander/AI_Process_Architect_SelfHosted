import argparse
import json
from pathlib import Path

from .analyst import extract_process_ir
from .exporters import generate_bpmn, generate_spec
from .exporters.n8n import SUPPORTED_TARGETS, export_n8n
from .validation import validate_process_ir
from .process_ir import upgrade_process_ir


def read_ir(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"WROTE {path}")


def report(path: Path, result) -> None:
    state = "PASS" if result.valid else "FAIL"
    print(f"{state} {path} ({result.counts.errors} errors, {result.counts.warnings} warnings)")
    for issue in result.issues:
        print(f"  {issue.severity.upper()} {issue.code} {issue.path}: {issue.message}")


def command_validate(paths: list[Path]) -> int:
    failed = False
    for path in paths:
        result = validate_process_ir(read_ir(path))
        report(path, result)
        failed = failed or not result.valid
    return int(failed)


def command_extract(input_path: Path, output_path: Path) -> int:
    result = extract_process_ir(input_path.read_text(encoding="utf-8"))
    write(output_path, json.dumps(result["process_ir"], ensure_ascii=False, indent=2) + "\n")
    print(f"MATCH {result['analysis']['scenarioId']} (confidence {result['analysis']['confidence']})")
    validation = validate_process_ir(result["process_ir"])
    report(output_path, validation)
    return int(not validation.valid)


def command_upgrade(input_path: Path, output_path: Path) -> int:
    process_ir = upgrade_process_ir(read_ir(input_path))
    validation = validate_process_ir(process_ir)
    write(output_path, json.dumps(process_ir, ensure_ascii=False, indent=2) + "\n")
    report(output_path, validation)
    return int(not validation.valid)


def command_spec(input_path: Path, output_path: Path) -> int:
    process_ir = read_ir(input_path)
    validation = validate_process_ir(process_ir)
    write(output_path, generate_spec(process_ir, validation))
    report(input_path, validation)
    return int(not validation.valid)


def command_spec_all(input_dir: Path, output_dir: Path) -> int:
    failed = False
    for input_path in sorted(input_dir.glob("*.process-ir.json")):
        output_path = output_dir / input_path.name.replace(".process-ir.json", ".spec.md")
        failed = bool(command_spec(input_path, output_path)) or failed
    return int(failed)


def command_n8n(input_path: Path, output_path: Path, target: str) -> int:
    process_ir = read_ir(input_path)
    validation = validate_process_ir(process_ir)
    if not validation.valid:
        report(input_path, validation)
        return 1
    write(output_path, json.dumps(export_n8n(process_ir, target), ensure_ascii=False, indent=2) + "\n")
    return 0


def command_bpmn(input_path: Path, output_path: Path) -> int:
    process_ir = read_ir(input_path)
    validation = validate_process_ir(process_ir)
    if not validation.valid:
        report(input_path, validation)
        return 1
    write(output_path, generate_bpmn(process_ir))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="process-architect")
    commands = root.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("paths", nargs="+", type=Path)
    extract = commands.add_parser("extract")
    extract.add_argument("input", type=Path)
    extract.add_argument("output", type=Path)
    upgrade = commands.add_parser("upgrade")
    upgrade.add_argument("input", type=Path)
    upgrade.add_argument("output", type=Path)
    spec = commands.add_parser("spec")
    spec.add_argument("input", type=Path)
    spec.add_argument("output", type=Path)
    spec_all = commands.add_parser("spec-all")
    spec_all.add_argument("input_dir", type=Path)
    spec_all.add_argument("output_dir", type=Path)
    n8n = commands.add_parser("n8n")
    n8n.add_argument("input", type=Path)
    n8n.add_argument("output", type=Path)
    n8n.add_argument("--target", choices=SUPPORTED_TARGETS, default=SUPPORTED_TARGETS[0])
    bpmn = commands.add_parser("bpmn")
    bpmn.add_argument("input", type=Path)
    bpmn.add_argument("output", type=Path)
    return root


def main() -> None:
    args = parser().parse_args()
    handlers = {
        "validate": lambda: command_validate(args.paths),
        "extract": lambda: command_extract(args.input, args.output),
        "upgrade": lambda: command_upgrade(args.input, args.output),
        "spec": lambda: command_spec(args.input, args.output),
        "spec-all": lambda: command_spec_all(args.input_dir, args.output_dir),
        "n8n": lambda: command_n8n(args.input, args.output, args.target),
        "bpmn": lambda: command_bpmn(args.input, args.output),
    }
    raise SystemExit(handlers[args.command]())


if __name__ == "__main__":
    main()
