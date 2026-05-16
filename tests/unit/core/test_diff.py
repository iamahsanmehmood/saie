import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from su_mcp_bridge.core.model import BuildingModel
from su_mcp_bridge.core.diff import diff_models

FIXTURE_PATH = Path(__file__).parent.parent.parent / "fixtures" / "house6x7.v2.json"

def test_diff_idempotency():
    with open(FIXTURE_PATH, 'r') as f:
        json_data = f.read()
    model1 = BuildingModel.model_validate_json(json_data)
    model2 = BuildingModel.model_validate_json(json_data)
    
    changeset = diff_models(model1, model2)
    assert changeset.is_empty()

def test_diff_modification():
    with open(FIXTURE_PATH, 'r') as f:
        json_data = f.read()
    model1 = BuildingModel.model_validate_json(json_data)
    model2 = BuildingModel.model_validate_json(json_data)
    
    # Modify thickness
    model2.levels[0].walls[0].thickness_mm = 200.0
    
    changeset = diff_models(model1, model2)
    assert not changeset.is_empty()
    assert len(changeset.modified) == 1
    mod = changeset.modified[0]
    assert mod.entity_id == "W1"
    assert mod.entity_type == "Wall"
    assert len(mod.changes) == 1
    assert mod.changes[0].field == "thickness_mm"
    assert mod.changes[0].old_value == 150.0
    assert mod.changes[0].new_value == 200.0

def test_diff_creation_and_deletion():
    with open(FIXTURE_PATH, 'r') as f:
        json_data = f.read()
    model1 = BuildingModel.model_validate_json(json_data)
    model2 = BuildingModel.model_validate_json(json_data)
    
    # Delete an opening
    del model2.levels[0].openings[0]
    
    # Create a new wall
    from su_mcp_bridge.core.model import Wall
    new_w = Wall(id="W3", level_id="GF", centerline=[[0,0], [0, 100]], thickness_mm=100, height_mm=2000)
    model2.levels[0].walls.append(new_w)
    
    changeset = diff_models(model1, model2)
    
    assert len(changeset.created) == 1
    assert changeset.created[0].entity_id == "W3"
    
    assert len(changeset.deleted) == 1
    assert changeset.deleted[0].entity_id == "WIN_BED1_F"
