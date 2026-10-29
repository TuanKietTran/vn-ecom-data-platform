"""Gold = dbt models, loaded as Dagster assets. dbt sources `silver.*` map onto the silver assets."""

import os
import sys
from pathlib import Path

import dagster as dg
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

from vnecom.gold import DBT_DIR, dbt_env, prepare_local_gold
from vnecom.settings import get_settings

# dbt reads these via env_var(); derive them from the same Settings the Spark jobs use
_s = get_settings()
for _k, _v in dbt_env(_s).items():
    os.environ.setdefault(_k, _v)
prepare_local_gold(_s)

dbt_project = DbtProject(project_dir=DBT_DIR, profiles_dir=DBT_DIR, target=os.getenv("DBT_TARGET", "lite"))
dbt_project.prepare_if_dev()  # `dagster dev` compiles the manifest on load


class GoldTranslator(DagsterDbtTranslator):
    """dbt layer -> Dagster group/key: marts become gold/<model>; everything refreshes eagerly
    once its upstream silver partitions land."""

    def get_asset_spec(self, manifest, unique_id, project):
        spec = super().get_asset_spec(manifest, unique_id, project)
        if unique_id.startswith("source."):
            return spec  # silver/<table> — matches the Spark assets
        node = manifest.get("nodes", {}).get(unique_id, {})
        fqn = node.get("fqn") or []
        layer = fqn[1] if node.get("resource_type") == "model" and len(fqn) > 2 else "ref"
        key = dg.AssetKey(["gold", node["name"]]) if layer == "marts" else spec.key
        return spec.replace_attributes(
            key=key,
            group_name={"marts": "gold", "staging": "dbt_staging", "intermediate": "dbt_intermediate"}.get(
                layer, "ref"
            ),
            automation_condition=dg.AutomationCondition.eager(),
        )


@dbt_assets(manifest=dbt_project.manifest_path, project=dbt_project, dagster_dbt_translator=GoldTranslator())
def gold_dbt(context: dg.AssetExecutionContext, dbt: DbtCliResource):
    from vnecom.pipeline import assert_publishable

    assert_publishable(get_settings())
    yield from dbt.cli(["build"], context=context).stream()


_venv_dbt = Path(sys.executable).with_name("dbt")  # prefer the dbt next to this interpreter
dbt_resource = DbtCliResource(
    project_dir=dbt_project, dbt_executable=str(_venv_dbt) if _venv_dbt.exists() else "dbt"
)
