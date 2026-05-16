import sys
import os
import json
import time

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src/python_client')))

from su_helpers import SketchUpBridge
from builder import BuilderAgent

def main():
    bridge = SketchUpBridge()
    if not bridge.wait_for_connection():
        print("Failed to connect to SketchUp")
        return
        
    print("Clearing model...")
    bridge.new_model()
    time.sleep(1) # Wait for model to clear
    
    with open(os.path.join(os.path.dirname(__file__), '../src/python_client/test_building.json')) as f:
        data = json.load(f)
        
    agent = BuilderAgent(bridge)
    state = agent.build_from_json(data)
    
    print("\n--- Final State ---")
    print(state.to_prompt_context())
    
    print("\nTaking screenshot...")
    bridge.set_camera(eye=[400, -200, 300], target=[118, 137, 50], fov=45)
    img_path = "C:/su_capture/test_builder_output.png"
    bridge.take_screenshot(img_path)
    print(f"Screenshot saved to {img_path}")

if __name__ == "__main__":
    main()
