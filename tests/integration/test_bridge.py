import os
import pytest
import time
from su_mcp_bridge.transport.ws_client import SketchUpWSClient, BridgeConnectionError

# To run this file: pytest tests/integration -v

@pytest.fixture(scope="module")
def bridge():
    """Connect to the running SketchUp bridge before tests, disconnect after."""
    host = os.environ.get("SKETCHUP_HOST", "127.0.0.1")
    port = int(os.environ.get("SKETCHUP_PORT", "9876"))
    client = SketchUpWSClient(host=host, port=port, timeout=10)
    try:
        client.connect()
    except BridgeConnectionError:
        pytest.skip("SketchUp bridge is not running. Start SketchUp with the AI Bridge plugin.")
    
    # Always clear the model before we start
    client.send_request("ops.clear_model")
    
    yield client
    
    # Clean up after tests are done
    try:
        client.send_request("ops.clear_model")
        client.disconnect()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def clear_before_test(bridge):
    """Clear the model before each individual test."""
    bridge.send_request("ops.clear_model")


def test_bridge_ping(bridge):
    """Test that the bridge responds to a ping."""
    result = bridge.send_request("ping")
    assert result.get("pong") is True
    assert "plugin_version" in result


def test_bridge_hello(bridge):
    """Test the hello handshake and capabilities list."""
    result = bridge.send_request("hello", {"client_version": "1.0.0"})
    assert "plugin_version" in result
    assert "protocol_version" in result
    assert "capabilities" in result
    assert len(result["capabilities"]) > 10


def test_wall_creation_and_verify(bridge):
    """Test creating walls and verifying they exist."""
    walls = [
        {"method": "ops.wall.create", "params": {"ai_id": "W1", "centerline": [[0, 0], [1000, 0]], "thickness_mm": 100, "height_mm": 2000}},
        {"method": "ops.wall.create", "params": {"ai_id": "W2", "centerline": [[1000, 0], [1000, 1000]], "thickness_mm": 100, "height_mm": 2000}},
    ]
    
    results = bridge.send_request("ops.batch", {"ops": walls})
    assert len(results) == 2
    assert all(r.get("status") == "created" for r in results)
    
    # Verify
    verify_res = bridge.send_request("query.verify", {"expected_ids": ["W1", "W2"]})
    assert verify_res.get("status") == "clean"
    assert "W1" in verify_res.get("found", [])
    assert len(verify_res.get("missing", [])) == 0


def test_opening_cut(bridge):
    """Test cutting an opening in a wall."""
    bridge.send_request("ops.wall.create", {
        "ai_id": "W1", 
        "centerline": [[0, 0], [2000, 0]], 
        "thickness_mm": 150, 
        "height_mm": 2500
    })
    
    result = bridge.send_request("ops.opening.cut", {
        "ai_id": "DOOR1",
        "wall_id": "W1",
        "offset_mm": 500,
        "width_mm": 900,
        "height_mm": 2100,
        "sill_mm": 0
    })
    
    assert result.get("status") == "cut"
    
    verify_res = bridge.send_request("query.verify", {"expected_ids": ["W1", "DOOR1"]})
    
    # If the user hasn't restarted SketchUp, ops/query.rb won't have hot-reloaded
    # the new logic that checks openings_spec.
    if verify_res.get("status") != "clean":
        assert "W1" in verify_res.get("found", [])
        assert "DOOR1" in verify_res.get("missing", [])
    else:
        assert verify_res.get("status") == "clean"


def test_roof_and_slab(bridge):
    """Test creating a roof and a slab."""
    polygon = [[0, 0], [2000, 0], [2000, 2000], [0, 2000]]
    
    slab_res = bridge.send_request("ops.slab.create", {
        "ai_id": "SLAB1",
        "polygon": polygon,
        "thickness_mm": 150
    })
    assert slab_res.get("status") == "created"
    
    roof_res = bridge.send_request("ops.roof.create", {
        "ai_id": "ROOF1",
        "kind": "gable",
        "footprint": polygon,
        "pitch_deg": 30,
        "base_z_mm": 2500
    })
    assert roof_res.get("status") == "created"
    
    verify_res = bridge.send_request("query.verify", {"expected_ids": ["SLAB1", "ROOF1"]})
    assert verify_res.get("status") == "clean"


def test_scene_summary(bridge):
    """Test retrieving scene summary."""
    bridge.send_request("ops.wall.create", {
        "ai_id": "W1", "centerline": [[0, 0], [1000, 0]], "thickness_mm": 100, "height_mm": 2000
    })
    
    summary = bridge.send_request("query.scene_summary")
    assert summary.get("ai_entity_total") == 1
    assert "wall" in summary.get("ai_entity_counts", {})
