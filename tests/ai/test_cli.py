import subprocess
import sys

from typer.testing import CliRunner

from vnecom import cli


def test_cli_import_does_not_import_optional_ai_frameworks_in_fresh_process():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import vnecom.cli; "
            "blocked = {'fastapi', 'langgraph', 'grpc'} & sys.modules.keys(); "
            "assert not blocked, f'optional modules imported: {blocked}'",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_ai_commands_show_help_without_optional_dependencies():
    runner = CliRunner()
    for args in (["--help"], ["ai", "--help"]):
        result = runner.invoke(cli.app, list(args))
        assert result.exit_code == 0, result.output
    for command in ("embed", "serve", "grpc", "eval", "match"):
        assert command in result.output


def test_ai_embed_invokes_pipeline_and_reports_unconfigured_backend(monkeypatch):
    from vnecom.ai.interfaces import embedding_factory

    monkeypatch.setattr(
        embedding_factory, "run_embedding_job_sync", lambda: {"processed": 3, "failed": 0, "indexed": 3}
    )
    result = CliRunner().invoke(cli.app, ["ai", "embed"])
    assert result.exit_code == 0, result.output
    assert '"indexed": 3' in result.output


def test_other_ai_stub_commands_report_unimplemented_behavior():
    runner = CliRunner()
    for command, expected in (
        ("grpc", "gRPC service is not implemented yet"),
        ("match", "product matching is not implemented yet"),
    ):
        result = runner.invoke(cli.app, ["ai", command])
        assert result.exit_code == 0, result.output
        assert expected in result.output


def test_ai_serve_reports_missing_extra(monkeypatch):
    import importlib.util

    original_find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name: None if name == "fastapi" else original_find_spec(name),
    )
    result = CliRunner().invoke(cli.app, ["ai", "serve"])
    assert result.exit_code == 2
    assert "pip install 'vnecom[ai]'" in result.output


def test_ai_serve_reports_missing_extra_when_factory_raises_runtime_error(monkeypatch):
    import vnecom.ai.interfaces.api as api

    def missing_dependencies():
        raise RuntimeError("missing API dependencies")

    monkeypatch.setattr(api, "create_app", missing_dependencies)
    result = CliRunner().invoke(cli.app, ["ai", "serve"])
    assert result.exit_code == 2
    assert "pip install 'vnecom[ai]'" in result.output
