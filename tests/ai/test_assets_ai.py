import os
import subprocess
import sys


def test_dagster_definitions_load_without_ai_extra():
    code = (
        "import importlib.util, sys; "
        "importlib.util.find_spec = lambda name: None if name == 'langgraph' "
        "else importlib.util.find_spec(name); "
        "import vnecom_dagster.definitions as d; "
        "assert d.defs is not None; "
        "import dagster as dg; dg.Definitions.validate_loadable(d.defs); "
        "assert 'vnecom_dagster.assets_ai' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": "orchestration/dagster"},
    )
    assert result.returncode == 0, result.stderr

