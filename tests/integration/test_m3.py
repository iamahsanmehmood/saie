"""
M3 Integration Test — Full house6x7 build + primitives + verify
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from su_mcp_bridge.transport.ws_client import SketchUpWSClient

def test_m3():
    client = SketchUpWSClient()
    client.connect()
    
    # === PHASE 1: Build the house (reuse proven v1 data) ===
    print("=== PHASE 1: Build House ===")
    client.send_request("ops.clear_model")
    time.sleep(0.3)
    
    ET, IT, H = 5.91, 3.94, 110.24
    HET = ET / 2.0
    
    walls = [
        {"id": "W1", "sx": -HET, "sy": 0, "ex": 118.11+HET, "ey": 0, "t": ET},
        {"id": "W5", "sx": 236.22+HET, "sy": 275.59, "ex": -HET, "ey": 275.59, "t": ET},
        {"id": "W6", "sx": 0, "sy": 275.59-HET, "ex": 0, "ey": HET, "t": ET},
        {"id": "W2", "sx": 118.11, "sy": HET, "ex": 118.11, "ey": 39.37-HET, "t": ET},
        {"id": "W3", "sx": 118.11-HET, "sy": 39.37, "ex": 236.22+HET, "ey": 39.37, "t": ET},
        {"id": "W4", "sx": 236.22, "sy": 39.37+HET, "ex": 236.22, "ey": 275.59-HET, "t": ET},
        {"id": "W_BED1_TOP", "sx": HET, "sy": 122.05, "ex": 118.11-HET/2, "ey": 122.05, "t": IT},
        {"id": "W_BED2_BOT", "sx": HET, "sy": 145.67, "ex": 118.11-HET/2, "ey": 145.67, "t": IT},
        {"id": "W_WC_RIGHT", "sx": 78.74, "sy": 122.05+IT/2, "ex": 78.74, "ey": 185.04-IT/2, "t": IT},
        {"id": "W_CENTER_TOP", "sx": 118.11, "sy": 177.17, "ex": 118.11, "ey": 275.59-HET, "t": IT},
        {"id": "W_CENTER_BOT", "sx": 118.11, "sy": 39.37+HET, "ex": 118.11, "ey": 122.05-IT/2, "t": IT},
    ]
    
    wall_ops = [{"method": "ops.wall.create", "params": {
        "ai_id": w["id"], "start_x": w["sx"], "start_y": w["sy"],
        "end_x": w["ex"], "end_y": w["ey"], "thickness": w["t"], "height": H
    }} for w in walls]
    
    results = client.send_request("ops.batch", {"ops": wall_ops})
    wall_guids = {}
    for i, w in enumerate(walls):
        r = results[i]
        if "error" not in r:
            wall_guids[w["id"]] = r["guid"]
    print(f"  Built {len(wall_guids)} walls")
    
    # Cut openings
    openings = [
        {"id": "WIN_BED1_F", "wid": "W1", "o": 19.69, "w": 78.74, "h": 59.06, "s": 23.62},
        {"id": "DOOR_FRONT", "wid": "W3", "o": 19.69, "w": 78.74, "h": 82.68, "s": 0},
        {"id": "WIN_LIVING", "wid": "W4", "o": 19.69, "w": 59.06, "h": 47.24, "s": 35.43},
        {"id": "WIN_KITCH_R", "wid": "W4", "o": 177.17, "w": 39.37, "h": 39.37, "s": 43.31},
        {"id": "WIN_KITCH_B", "wid": "W5", "o": 19.69, "w": 39.37, "h": 39.37, "s": 43.31},
        {"id": "WIN_BED2_B", "wid": "W5", "o": 157.48, "w": 59.06, "h": 47.24, "s": 35.43},
        {"id": "WIN_BED2_L", "wid": "W6", "o": 19.69, "w": 59.06, "h": 47.24, "s": 35.43},
        {"id": "WIN_WC", "wid": "W6", "o": 110.24, "w": 23.62, "h": 23.62, "s": 59.06},
        {"id": "WIN_BED1_L", "wid": "W6", "o": 196.85, "w": 59.06, "h": 47.24, "s": 35.43},
        {"id": "DOOR_BED1", "wid": "W_BED1_TOP", "o": 82.68, "w": 31.5, "h": 82.68, "s": 0},
        {"id": "DOOR_BED2", "wid": "W_BED2_BOT", "o": 82.68, "w": 31.5, "h": 82.68, "s": 0},
        {"id": "DOOR_WC", "wid": "W_WC_RIGHT", "o": 15.75, "w": 27.56, "h": 82.68, "s": 0},
    ]
    
    for op in openings:
        if op["wid"] not in wall_guids:
            continue
        res = client.send_request("ops.opening.cut", {
            "ai_id": op["id"], "wall_id": op["wid"],
            "offset": op["o"], "width": op["w"], "height": op["h"], "sill": op["s"]
        })
        if res.get("result_guid"):
            wall_guids[op["wid"]] = res["result_guid"]
        time.sleep(0.1)
    print(f"  Cut {len(openings)} openings")
    
    # === PHASE 2: Add a floor slab ===
    print("\n=== PHASE 2: Add Floor Slab ===")
    slab_res = client.send_request("ops.slab.create", {
        "ai_id": "SLAB_GF",
        "polygon": [[0,0], [236.22*25.4, 0], [236.22*25.4, 39.37*25.4], 
                     [118.11*25.4, 39.37*25.4], [118.11*25.4, 0],
                     [0, 0]],  # simplified
        "thickness_mm": 150,
        "top_or_bottom": "bottom",
        "base_z_mm": 0
    })
    # Simpler rectangular slab
    client.send_request("ops.clear_model")  # Reset
    time.sleep(0.2)
    
    # Rebuild walls quickly
    results = client.send_request("ops.batch", {"ops": wall_ops})
    wall_guids = {}
    for i, w in enumerate(walls):
        r = results[i]
        if "error" not in r:
            wall_guids[w["id"]] = r["guid"]
    
    for op in openings:
        if op["wid"] not in wall_guids:
            continue
        res = client.send_request("ops.opening.cut", {
            "ai_id": op["id"], "wall_id": op["wid"],
            "offset": op["o"], "width": op["w"], "height": op["h"], "sill": op["s"]
        })
        if res.get("result_guid"):
            wall_guids[op["wid"]] = res["result_guid"]
        time.sleep(0.1)
    
    # === PHASE 3: Add primitives ===
    print("\n=== PHASE 3: Test Primitives ===")
    primitives = [
        {"ai_id": "PRIM_BOX", "kind": "box", 
         "dimensions": {"width_mm": 500, "depth_mm": 500, "height_mm": 500},
         "transform": {"position_mm": [-2000, 0, 0]}},
        {"ai_id": "PRIM_CYL", "kind": "cylinder",
         "dimensions": {"radius_mm": 300, "height_mm": 800},
         "transform": {"position_mm": [-2000, 2000, 0]}},
        {"ai_id": "PRIM_PYRAMID", "kind": "pyramid",
         "dimensions": {"width_mm": 600, "depth_mm": 600, "height_mm": 900},
         "transform": {"position_mm": [-2000, 4000, 0]}},
    ]
    
    prim_ops = [{"method": "ops.primitive.create", "params": p} for p in primitives]
    prim_results = client.send_request("ops.batch", {"ops": prim_ops})
    for i, p in enumerate(primitives):
        r = prim_results[i]
        status = r.get("status", r.get("error", "?"))
        print(f"  {p['ai_id']} ({p['kind']}): {status}")
    
    # === PHASE 4: Verify ===
    print("\n=== PHASE 4: Verify ===")
    expected_ids = [w["id"] for w in walls] + [p["ai_id"] for p in primitives]
    verify_res = client.send_request("query.verify", {"expected_ids": expected_ids})
    print(f"  Found: {len(verify_res.get('found', []))}")
    print(f"  Missing: {verify_res.get('missing', [])}")
    print(f"  Orphans: {verify_res.get('orphans', [])}")
    print(f"  Divergences: {verify_res.get('divergences', 0)}")
    print(f"  Status: {verify_res.get('status', '?')}")
    
    # === PHASE 5: Final captures ===
    print("\n=== PHASE 5: Captures ===")
    for preset in ["iso", "plan"]:
        res = client.send_request("view.capture", {"preset": preset, "width": 1920, "height": 1080})
        print(f"  [{preset}] -> {res.get('path', '?')}")
        time.sleep(0.2)
    
    # === PHASE 6: Export JSON ===
    print("\n=== PHASE 6: Export JSON ===")
    export = client.send_request("query.export_json", {})
    print(f"  Total entities in model: {export.get('total', 0)}")
    
    print("\n=== M3 TEST COMPLETE ===")
    client.disconnect()

if __name__ == "__main__":
    test_m3()
