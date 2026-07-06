"""Command-line interface for the local sprite production pipeline."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any

from PIL import Image

from sprite_builder.batch import batch_status, load_batch, prepare_batch
from sprite_builder.character import analyze_reference, create_character_skeleton
from sprite_builder.domain.config import load_job
from sprite_builder.domain.models import JobSpec
from sprite_builder.generation import (
    GenerationRequest,
    PromptCompiler,
    build_character_context,
    ingest_candidate,
    latest_request_decision,
    prepare_requests,
    record_request_decision,
)
from sprite_builder.pipeline import (
    align_job,
    export_job,
    postprocess_job,
    preview_job,
    validate_job,
)
from sprite_builder.sheets import (
    AutoCenterConfig,
    BackgroundRemovalConfig,
    SegmentationConfig,
    SheetSessionStore,
    apply_background_removal,
    auto_center_frames,
    segment_sheet,
)


def _workspace(value: str) -> Path:
    return Path(value).resolve()


class _NormalizingArgumentParser(argparse.ArgumentParser):
    def parse_args(self, args: list[str] | None = None, namespace: argparse.Namespace | None = None):
        return super().parse_args(_normalize_argv(args), namespace)


def _request(path: str | Path) -> GenerationRequest:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    allowed = {field.name for field in fields(GenerationRequest)}
    value = {key: item for key, item in value.items() if key in allowed}
    value["reference_paths"] = tuple(value.get("reference_paths", ()))
    value["source_size"] = tuple(value.get("source_size", (1024, 1024)))
    return GenerationRequest(**value)


def _palette_for(job: Any) -> Path:
    return Path(job.character.bible).parent / "palette.json"


def _normalize_argv(argv: list[str] | None) -> list[str] | None:
    if argv is None:
        return None
    tokens = list(argv)
    workspace: str | None = None
    normalized: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--workspace" and index + 1 < len(tokens):
            workspace = tokens[index + 1]
            index += 2
            continue
        normalized.append(token)
        index += 1
    if workspace is not None:
        normalized = ["--workspace", workspace, *normalized]
    return normalized


def _json_print(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _rgb_hex(value: str) -> tuple[int, int, int]:
    raw = value.strip().lstrip("#")
    if len(raw) != 6:
        raise argparse.ArgumentTypeError("Expected a colour in #RRGGBB format")
    try:
        return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected a colour in #RRGGBB format") from exc


def command_doctor(args: argparse.Namespace) -> int:
    checks = {
        "python": platform.python_version(),
        "workspace": str(_workspace(args.workspace)),
        "pillow": False,
        "numpy": False,
        "opencv": False,
        "openai_api_used": False,
        "codex_skill": (
            _workspace(args.workspace) / ".codex/skills/sprite-builder/SKILL.md"
        ).is_file(),
    }
    for module, key in (("PIL", "pillow"), ("numpy", "numpy"), ("cv2", "opencv")):
        try:
            __import__(module)
            checks[key] = True
        except ImportError:
            pass
    _json_print(checks)
    return 0 if all(checks[key] for key in ("pillow", "numpy", "opencv", "codex_skill")) else 2


def command_reference_analyze(args: argparse.Namespace) -> int:
    analysis = analyze_reference(args.image, palette_colors=args.palette_colors)
    value = analysis.to_dict()
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    _json_print(value)
    return 0


def command_character_create(args: argparse.Namespace) -> int:
    result = create_character_skeleton(
        args.id,
        args.description,
        workspace=_workspace(args.workspace),
        reference=args.reference,
        palette_colors=args.palette_colors,
    )
    _json_print(
        {
            "directory": str(result.directory),
            "bible": str(result.bible),
            "palette": str(result.palette),
            "reference_analyzed": result.analysis is not None,
            "review_required": True,
        }
    )
    return 0


def command_prepare(args: argparse.Namespace) -> int:
    root = _workspace(args.workspace)
    job = load_job(args.job)
    compiler = PromptCompiler(root / "prompts")
    requests = prepare_requests(
        job,
        workspace=root,
        prompt_compiler=compiler,
        character_context=build_character_context(job, workspace=root),
    )
    _json_print({"job_id": job.job_id, "prepared": len(requests)})
    return 0


def command_queue(args: argparse.Namespace) -> int:
    root = _workspace(args.workspace)
    request_dir = root / "jobs" / args.job_id / "generation" / "requests"
    index_path = request_dir / "index.json"
    if index_path.exists():
        request_ids = json.loads(index_path.read_text(encoding="utf-8")).get("request_ids", [])
        request_paths = [request_dir / f"{request_id}.json" for request_id in request_ids]
    else:
        request_paths = sorted(request_dir.glob("*.json"))
    records = []
    for path in request_paths:
        if path.name == "index.json":
            continue
        request = _request(path)
        raw = root / "jobs" / args.job_id / "raw" / request.output_filename
        decision = latest_request_decision(
            request.request_id,
            job_id=request.job_id,
            workspace=root,
        )
        records.append(
            {
                "request_id": request.request_id,
                "frame": request.frame_index,
                "candidate": request.candidate_index,
                "status": (
                    decision.status
                    if decision is not None
                    else "ingested"
                    if raw.exists()
                    else "pending"
                ),
                "source_kind": request.source_kind,
                "seed_source": request.seed_source_path,
                "request": str(path),
                "expected_output": str(raw),
            }
        )
    _json_print({"job_id": args.job_id, "requests": records})
    return 0


def command_ingest(args: argparse.Namespace) -> int:
    record = ingest_candidate(
        _request(args.request), args.image, workspace=_workspace(args.workspace)
    )
    _json_print(
        record.__dict__
        if hasattr(record, "__dict__")
        else {field.name: getattr(record, field.name) for field in fields(record)}
    )
    return 0


def command_request_review(args: argparse.Namespace) -> int:
    decision = record_request_decision(
        _request(args.request),
        args.status,
        workspace=_workspace(args.workspace),
        notes=args.notes or "",
    )
    _json_print(decision.to_dict())
    return 0


def command_batch_prepare(args: argparse.Namespace) -> int:
    _json_print(prepare_batch(load_batch(args.batch), workspace=_workspace(args.workspace)))
    return 0


def command_batch_status(args: argparse.Namespace) -> int:
    _json_print(batch_status(load_batch(args.batch), workspace=_workspace(args.workspace)))
    return 0


def command_ui(args: argparse.Namespace) -> int:
    try:
        import streamlit  # noqa: F401
    except ImportError:
        print(
            "sprite-builder UI requires optional dependencies. "
            "Install them with: python -m pip install -e '.[ui]'",
            file=sys.stderr,
        )
        return 2
    app = Path(__file__).parent / "ui" / "app.py"
    workspace = _workspace(args.workspace)
    environment = os.environ.copy()
    environment["SPRITE_BUILDER_WORKSPACE"] = str(workspace)
    src_path = str(workspace / "src")
    existing_pythonpath = environment.get("PYTHONPATH", "")
    if existing_pythonpath:
        environment["PYTHONPATH"] = os.pathsep.join((src_path, existing_pythonpath))
    else:
        environment["PYTHONPATH"] = src_path
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app),
        "--server.address",
        args.host,
        "--server.port",
        str(args.port),
        "--browser.gatherUsageStats",
        "false",
    ]
    if args.no_browser:
        command.extend(("--server.headless", "true"))
    return int(subprocess.call(command, env=environment))


def command_sheet_session_create(args: argparse.Namespace) -> int:
    store = SheetSessionStore(_workspace(args.workspace))
    session = store.create(args.image, source_name=Path(args.image).name)
    _json_print(session.to_dict())
    return 0


def command_sheet_process(args: argparse.Namespace) -> int:
    root = _workspace(args.workspace)
    store = SheetSessionStore(root)
    session = store.load(args.session)
    with Image.open(store.source_path(session)) as source_image:
        source = source_image.convert("RGBA")
    segmentation_config = SegmentationConfig(
        frame_count=args.frame_count,
        orientation=args.orientation,
        rows=args.rows,
        columns=args.columns,
        cell_width=args.cell_width,
        cell_height=args.cell_height,
        offset_x=args.offset_x,
        offset_y=args.offset_y,
        spacing_x=args.spacing_x,
        spacing_y=args.spacing_y,
    )
    segmented = segment_sheet(
        source,
        segmentation_config,
        background_rgb=session.inspection.border_rgb,
    )
    background_config = BackgroundRemovalConfig(
        color=args.background_color or session.inspection.border_rgb,
        tolerance=args.tolerance,
        cleanup_enabled=not args.no_cleanup,
        fringe_cleanup_strength=args.fringe_cleanup,
        remove_near_transparent=args.remove_near_transparent,
        preserve_outline=not args.no_preserve_outline,
    )
    transparent = apply_background_removal(segmented.frames, background_config)
    assert segmented.resolved_config.cell_width is not None
    assert segmented.resolved_config.cell_height is not None
    canvas_width = args.canvas_width or segmented.resolved_config.cell_width
    canvas_height = args.canvas_height or segmented.resolved_config.cell_height
    anchor = (
        args.anchor_x if args.anchor_x is not None else canvas_width // 2,
        args.anchor_y if args.anchor_y is not None else round(canvas_height * 0.55),
    )
    center_config = AutoCenterConfig(
        method=args.center_method,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        canonical_anchor=anchor,
        confidence_threshold=args.confidence_threshold,
    )
    previous = {
        item.frame_index: item
        for item in session.frame_adjustments
        if item.frame_index < len(transparent)
    }
    centered = auto_center_frames(
        transparent,
        center_config,
        manual_offsets=[
            (
                previous[index].manual_offset_x if index in previous else 0,
                previous[index].manual_offset_y if index in previous else 0,
            )
            for index in range(len(transparent))
        ],
        locked=[
            previous[index].locked if index in previous else False
            for index in range(len(transparent))
        ],
        notes=[
            previous[index].notes if index in previous else ""
            for index in range(len(transparent))
        ],
    )
    session.segmentation_config = segmentation_config
    session.background_removal_config = background_config
    session.auto_center_config = center_config
    store.commit_stage(
        session,
        "segmentation",
        segmented.frames,
        config=segmentation_config.to_dict(),
        warnings=segmented.warnings,
        metadata={
            "regions": [list(region) for region in segmented.regions],
            "resolved_config": segmented.resolved_config.to_dict(),
        },
    )
    store.commit_stage(
        session,
        "background",
        transparent,
        config={
            "segmentation": segmentation_config.to_dict(),
            "background": background_config.to_dict(),
        },
    )
    store.commit_stage(
        session,
        "alignment",
        centered.frames,
        config={
            "segmentation": segmentation_config.to_dict(),
            "background": background_config.to_dict(),
            "auto_center": center_config.to_dict(),
        },
        status=centered.status,
        metrics=centered.jitter_report,
        metadata={"frames": [item.to_dict() for item in centered.adjustments]},
    )
    store.save_adjustments(session, centered.adjustments)
    _json_print(
        {
            "session_id": session.session_id,
            "status": centered.status,
            "frames": len(centered.frames),
            "warnings": segmented.warnings,
            "jitter": centered.jitter_report,
        }
    )
    return 3 if centered.status == "manual_review" else 0


def command_sheet_export(args: argparse.Namespace) -> int:
    root = _workspace(args.workspace)
    store = SheetSessionStore(root)
    session = store.load(args.session)
    paths = store.stage_paths(session, "alignment")
    if not paths:
        raise FileNotFoundError("No aligned sheet-session frames; run sheet-process first")
    frames = [Image.open(path).convert("RGBA") for path in paths]
    manifest = store.export(
        session,
        frames,
        layout=args.layout,
        columns=args.columns,
        export_frames=not args.no_frames,
        export_contact_sheet=not args.no_contact_sheet,
        export_gif=args.gif,
        fps=args.fps,
    )
    _json_print(manifest)
    return 0


def _load(args: argparse.Namespace) -> tuple[JobSpec, Path]:
    return load_job(args.job), _workspace(args.workspace)


def command_postprocess(args: argparse.Namespace) -> int:
    job, root = _load(args)
    _json_print(
        {
            "frames": [
                str(path)
                for path in postprocess_job(job, workspace=root, palette_path=_palette_for(job))
            ]
        }
    )
    return 0


def command_align(args: argparse.Namespace) -> int:
    job, root = _load(args)
    paths, anchors = align_job(job, workspace=root, overrides_path=args.overrides)
    _json_print({"frames": [str(path) for path in paths], "anchors": anchors})
    return 3 if any(item["manual_review"] for item in anchors) else 0


def command_validate(args: argparse.Namespace) -> int:
    job, root = _load(args)
    report = validate_job(job, workspace=root, palette_path=_palette_for(job))
    _json_print(report)
    return {"pass": 0, "review": 3, "reject": 4}.get(report["status"], 4)


def command_preview(args: argparse.Namespace) -> int:
    job, root = _load(args)
    _json_print(preview_job(job, workspace=root))
    return 0


def command_export(args: argparse.Namespace) -> int:
    job, root = _load(args)
    _json_print(export_job(job, workspace=root))
    return 0


def command_run(args: argparse.Namespace) -> int:
    job, root = _load(args)
    if args.dry_run:
        return command_prepare(args)
    postprocess_job(job, workspace=root, palette_path=_palette_for(job))
    _, anchors = align_job(job, workspace=root, overrides_path=args.overrides)
    if any(item["manual_review"] for item in anchors) and not args.allow_review:
        _json_print({"status": "manual_review", "reason": "low-confidence torso anchor"})
        return 3
    report = validate_job(job, workspace=root, palette_path=_palette_for(job))
    if report["status"] == "reject":
        _json_print(report)
        return 4
    previews = preview_job(job, workspace=root)
    outputs = export_job(job, workspace=root)
    _json_print({"status": report["status"], "previews": previews, "outputs": outputs})
    return 0 if report["status"] == "pass" else 3


def build_parser() -> argparse.ArgumentParser:
    parser = _NormalizingArgumentParser(prog="sprite-builder")
    parser.add_argument("--workspace", default=".")
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor")
    doctor.set_defaults(func=command_doctor)
    reference_analyze = commands.add_parser("reference-analyze")
    reference_analyze.add_argument("--image", required=True)
    reference_analyze.add_argument("--palette-colors", type=int, default=16)
    reference_analyze.add_argument("--output")
    reference_analyze.set_defaults(func=command_reference_analyze)
    character_create = commands.add_parser("character-create")
    character_create.add_argument("--id", required=True)
    character_create.add_argument("--description", required=True)
    character_create.add_argument("--reference")
    character_create.add_argument("--palette-colors", type=int, default=16)
    character_create.set_defaults(func=command_character_create)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--job", required=True)
    prepare.set_defaults(func=command_prepare)
    queue = commands.add_parser("queue")
    queue.add_argument("--job-id", required=True)
    queue.set_defaults(func=command_queue)
    ingest = commands.add_parser("ingest")
    ingest.add_argument("--request", required=True)
    ingest.add_argument("--image", required=True)
    ingest.set_defaults(func=command_ingest)
    request_review = commands.add_parser("request-review")
    request_review.add_argument("--request", required=True)
    request_review.add_argument("--status", choices=("accepted", "rejected"), required=True)
    request_review.add_argument("--notes")
    request_review.set_defaults(func=command_request_review)
    batch_prepare = commands.add_parser("batch-prepare")
    batch_prepare.add_argument("--batch", required=True)
    batch_prepare.set_defaults(func=command_batch_prepare)
    batch_status_parser = commands.add_parser("batch-status")
    batch_status_parser.add_argument("--batch", required=True)
    batch_status_parser.set_defaults(func=command_batch_status)
    ui = commands.add_parser("ui")
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--port", type=int, default=8501)
    ui.add_argument("--no-browser", action="store_true")
    ui.set_defaults(func=command_ui)
    sheet_create = commands.add_parser("sheet-session-create")
    sheet_create.add_argument("--image", required=True)
    sheet_create.set_defaults(func=command_sheet_session_create)
    sheet_process = commands.add_parser("sheet-process")
    sheet_process.add_argument("--session", required=True)
    sheet_process.add_argument("--frame-count", type=int, required=True)
    sheet_process.add_argument(
        "--orientation",
        choices=("horizontal", "vertical", "grid"),
        default="horizontal",
    )
    sheet_process.add_argument("--rows", type=int, default=1)
    sheet_process.add_argument("--columns", type=int, default=1)
    sheet_process.add_argument("--cell-width", type=int)
    sheet_process.add_argument("--cell-height", type=int)
    sheet_process.add_argument("--offset-x", type=int, default=0)
    sheet_process.add_argument("--offset-y", type=int, default=0)
    sheet_process.add_argument("--spacing-x", type=int, default=0)
    sheet_process.add_argument("--spacing-y", type=int, default=0)
    sheet_process.add_argument("--background-color", type=_rgb_hex)
    sheet_process.add_argument("--tolerance", type=float, default=24)
    sheet_process.add_argument("--no-cleanup", action="store_true")
    sheet_process.add_argument("--fringe-cleanup", type=int, default=1)
    sheet_process.add_argument("--remove-near-transparent", action="store_true")
    sheet_process.add_argument("--no-preserve-outline", action="store_true")
    sheet_process.add_argument(
        "--center-method",
        choices=("body", "bounding_box"),
        default="body",
    )
    sheet_process.add_argument("--canvas-width", type=int)
    sheet_process.add_argument("--canvas-height", type=int)
    sheet_process.add_argument("--anchor-x", type=int)
    sheet_process.add_argument("--anchor-y", type=int)
    sheet_process.add_argument("--confidence-threshold", type=float, default=0.65)
    sheet_process.set_defaults(func=command_sheet_process)
    sheet_export = commands.add_parser("sheet-export")
    sheet_export.add_argument("--session", required=True)
    sheet_export.add_argument(
        "--layout",
        choices=("horizontal", "vertical", "grid"),
        default="horizontal",
    )
    sheet_export.add_argument("--columns", type=int)
    sheet_export.add_argument("--no-frames", action="store_true")
    sheet_export.add_argument("--no-contact-sheet", action="store_true")
    sheet_export.add_argument("--gif", action="store_true")
    sheet_export.add_argument("--fps", type=float, default=8)
    sheet_export.set_defaults(func=command_sheet_export)
    for name, function in (
        ("postprocess", command_postprocess),
        ("align", command_align),
        ("validate", command_validate),
        ("preview", command_preview),
        ("export", command_export),
        ("run", command_run),
    ):
        command = commands.add_parser(name)
        command.add_argument("--job", required=True)
        if name in {"align", "run"}:
            command.add_argument("--overrides")
        if name == "run":
            command.add_argument("--dry-run", action="store_true")
            command.add_argument("--allow-review", action="store_true")
        command.set_defaults(func=function)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(_normalize_argv(argv))
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"sprite-builder: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
