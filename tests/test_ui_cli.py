from __future__ import annotations

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
        "batch-prepare",
        "batch-status",
        "postprocess",
        "align",
        "validate",
        "preview",
        "export",
        "run",
        "request-review",
        "sheet-session-create",
        "sheet-process",
        "sheet-export",
    ):
        assert command in parser.format_help()


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
