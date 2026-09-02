from __future__ import annotations

import pytest

from sprite_builder.cli import build_parser


def test_ui_command_is_additive_and_workspace_remains_global() -> None:
    parser = build_parser()
    args = parser.parse_args(
        ["--workspace", "/tmp/sprites", "ui", "--port", "8765", "--no-browser"]
    )
    assert args.command == "ui"
    assert args.workspace == "/tmp/sprites"
    assert args.port == 8765
    assert args.no_browser is True


def test_ui_command_accepts_workspace_after_subcommand() -> None:
    parser = build_parser()
    args = parser.parse_args(
        ["ui", "--workspace", "/tmp/sprites", "--port", "8765", "--no-browser"]
    )
    assert args.command == "ui"
    assert args.workspace == "/tmp/sprites"
    assert args.port == 8765
    assert args.no_browser is True


def test_existing_cli_commands_remain_available() -> None:
    parser = build_parser()
    for command in (
        "doctor",
        "reference-analyze",
        "character-create",
        "prepare",
        "queue",
        "ingest",
        "generate-openai",
        "request-review",
        "batch-prepare",
        "batch-status",
        "sheet-session-create",
        "sheet-process",
        "sheet-export",
        "sheet-native-export",
        "sheet-source-validate",
    ):
        assert command in parser.format_help()


def test_removed_frame_pipeline_commands_are_not_available() -> None:
    parser = build_parser()
    for command in ("postprocess", "align", "validate", "preview", "export", "run"):
        with pytest.raises(SystemExit):
            parser.parse_args([command, "--job", "configs/job.yaml"])


def test_headless_sheet_commands_parse_real_surface() -> None:
    parser = build_parser()
    process = parser.parse_args(
        [
            "sheet-process",
            "--session",
            "sheet-1",
            "--frame-count",
            "4",
            "--orientation",
            "grid",
            "--rows",
            "2",
            "--columns",
            "2",
        ]
    )
    assert process.command == "sheet-process"
    assert process.rows * process.columns == process.frame_count


def test_native_sheet_export_requires_regions_and_preserves_explicit_indices() -> None:
    parser = build_parser()
    native = parser.parse_args(
        [
            "sheet-native-export",
            "--session",
            "sheet-1",
            "--animation",
            "save_prepare",
            "--output-dir",
            "exports/save_prepare",
            "--texture-resource-path",
            "res://assets/save/native.png",
            "--frame-indices",
            "0,1,2,3",
        ]
    )
    assert native.command == "sheet-native-export"
    assert native.frame_indices == (0, 1, 2, 3)
    assert native.loop is False


def test_sheet_source_validate_command_parses_job() -> None:
    parser = build_parser()
    args = parser.parse_args(["sheet-source-validate", "--job", "configs/job.yaml"])
    assert args.command == "sheet-source-validate"
    assert args.job == "configs/job.yaml"
