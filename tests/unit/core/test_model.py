import os
import sys
import pytest
from pathlib import Path

# Adjust path so pytest can find src
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from su_mcp_bridge.core.model import BuildingModel
from su_mcp_bridge.core.validate import validate_model

FIXTURE_PATH = Path(__file__).parent.parent.parent / "fixtures" / "house6x7.v2.json"

def test_model_load_and_validate():
    with open(FIXTURE_PATH, 'r') as f:
        json_data = f.read()
        
    model = BuildingModel.model_validate_json(json_data)
    assert model.project.name == "House 6x7 v2"
    assert len(model.levels) == 1
    assert len(model.levels[0].walls) == 2
    assert len(model.levels[0].openings) == 1
    
    # Test our semantic validation
    issues = validate_model(model)
    assert len(issues) == 0, f"Found validation issues: {issues}"

def test_validation_dangling_id():
    with open(FIXTURE_PATH, 'r') as f:
        json_data = f.read()
    model = BuildingModel.model_validate_json(json_data)
    
    # Intentionally corrupt the wall reference
    model.levels[0].openings[0].wall_id = "INVALID_W"
    
    issues = validate_model(model)
    assert len(issues) == 1
    assert issues[0].entity_id == "WIN_BED1_F"
    assert "non-existent wall_id" in issues[0].message
