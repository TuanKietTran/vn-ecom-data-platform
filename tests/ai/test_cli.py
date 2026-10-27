import sys
from types import ModuleType

from typer.testing import CliRunner

from vnecom import cli


def test_ai_status_is_a_stub():
    result = CliRunner().invoke(cli.app, ["ai", "status"])
    assert result.exit_code == 0
    assert "stub" in result.output


def test_cli_import_does_not_import_ai_infrastructure():
    assert "vnecom.ai.config" not in sys.modules
    assert "litellm" not in sys.modules


def test_ai_command_group_has_help():
    result = CliRunner().invoke(cli.app, ["ai", "--help"])
    assert result.exit_code == 0
    assert "status" in result.output
