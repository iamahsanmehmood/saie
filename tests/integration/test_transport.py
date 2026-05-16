import sys
import time
from pathlib import Path

# Insert e:\Devs\TEst\1\src into sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from su_mcp_bridge.transport.ws_client import SketchUpWSClient

def test_ping():
    client = SketchUpWSClient()
    print("Connecting to SketchUp WebSocket...")
    client.connect()
    
    # Send 100 pings and measure latency
    latencies = []
    for i in range(100):
        start = time.time()
        res = client.send_request("ping")
        end = time.time()
        latencies.append((end - start) * 1000) # ms
        
    avg = sum(latencies) / len(latencies)
    print(f"Average Ping Latency over 100 requests: {avg:.2f} ms")
    assert avg < 150.0, f"Ping too slow! Avg: {avg}ms"
    client.disconnect()

def test_50_wall_batch():
    client = SketchUpWSClient()
    client.connect()
    
    ops = []
    for i in range(50):
        # Create a line of walls side by side
        y = i * 200 # 200mm apart
        ops.append({
            "method": "ops.wall.create",
            "params": {
                "ai_id": f"TEST_WALL_{i}",
                "centerline": [[0, y], [3000, y]],
                "thickness_mm": 150.0,
                "height_mm": 2800.0
            }
        })
    
    print(f"Sending batch of {len(ops)} wall creations...")
    start = time.time()
    res = client.send_request("ops.batch", {"ops": ops})
    end = time.time()
    
    dur = end - start
    print(f"Batch completed in {dur:.2f} seconds.")
    assert dur < 5.0, f"Batch too slow! Took {dur}s"
    assert len(res) == 50
    assert res[0]["status"] == "created"
    
    client.disconnect()

if __name__ == "__main__":
    print("WARNING: This test requires SketchUp 2025 to be running with the AI Bridge v2 loaded.")
    test_ping()
    test_50_wall_batch()
    print("All integration tests passed locally.")
