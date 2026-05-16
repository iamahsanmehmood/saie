"""
cli/sb.py — SketchUp Builder CLI
==================================

Entry point for the `sb` command-line tool.

Usage:
    sb status                          Show bridge + model status
    sb ping                            Test bridge connectivity
    sb clear                           Clear the SketchUp model
    sb summary                         Scene summary (token-efficient)
    sb scan                            Deep scan (full introspection)
    sb report [--format md|csv|json]   Generate a model report
    sb clash                           Run clash detection
    sb verify W1 W2 DOOR_1             Verify entity IDs exist
    sb capture [iso|plan|elev_*]       Capture a view
    sb capture-all                     Capture all 6 canonical views
    sb walkthrough [orbit|flythrough]  Generate walkthrough video
    sb render                          HQ isometric render
    sb save [path]                     Save the model
    sb new                             Create a new file
    sb open <path>                     Open a .skp file
    sb model-info                      Get model metadata
    sb project create|list|open|info   Project management
    sb agent "Build a house"           Start the AI agent with a prompt
    sb agent                           Start interactive agent REPL
    sb mcp                             Start the MCP server (stdio)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

# Ensure src/ is importable.
_src = os.path.join(os.path.dirname(__file__), "..", "..")
if _src not in sys.path:
    sys.path.insert(0, os.path.abspath(_src))


def _get_client():
    """Lazy-import and return a connected bridge client."""
    from su_mcp_bridge.transport.ws_client import SketchUpWSClient

    host = os.environ.get("SKETCHUP_HOST", "localhost")
    port_env = os.environ.get("SKETCHUP_PORT")
    port = int(port_env) if port_env else None
    # Use a large timeout (600s) because cinematic walkthroughs or heavy renders can take minutes.
    client = SketchUpWSClient(host=host, port=port, timeout=600.0)
    client.connect()
    return client


def _print_json(data):
    """Print JSON with UTF-8 encoding."""
    print(json.dumps(data, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_ping(_args):
    """Test bridge connectivity."""
    try:
        client = _get_client()
        t0 = time.time()
        result = client.send_request("ping")
        t1 = time.time()
        latency = round((t1 - t0) * 1000, 2)
        print(f"PONG  plugin_v{result.get('plugin_version', '?')} (latency: {latency}ms)")
        client.disconnect()
    except Exception as e:
        print(f"FAIL  {e}")
        sys.exit(1)


def cmd_status(_args):
    """Show bridge status + scene summary."""
    try:
        client = _get_client()
        hello = client.send_request("hello", {"client_version": "1.0.0"})
        summary = client.send_request("query.scene_summary")
        client.disconnect()

        print("Bridge:     connected")
        print(f"Plugin:     v{hello.get('plugin_version', '?')}")
        print(f"Protocol:   v{hello.get('protocol_version', '?')}")
        print(f"Methods:    {len(hello.get('capabilities', []))}")
        print(f"Model:      '{summary.get('title', 'Untitled')}'")
        print(f"Entities:   {summary.get('ai_entity_total', 0)} AI-tracked")
        counts = summary.get("ai_entity_counts", {})
        if counts:
            parts = [f"{v} {k}{'s' if v != 1 else ''}" for k, v in counts.items()]
            print(f"            ({', '.join(parts)})")
        print(f"Layers:     {', '.join(summary.get('layer_names', []))}")
    except Exception as e:
        print(f"Bridge:     DISCONNECTED ({e})")
        sys.exit(1)


def cmd_clear(_args):
    """Clear the model."""
    client = _get_client()
    result = client.send_request("ops.clear_model")
    print(f"Model cleared: {result.get('status', 'ok')}")
    client.disconnect()


def cmd_summary(_args):
    """Scene summary."""
    client = _get_client()
    result = client.send_request("query.scene_summary")
    _print_json(result)
    client.disconnect()


def cmd_verify(args):
    """Verify entity IDs exist."""
    if not args.ids:
        print("Usage: sb verify W1 W2 DOOR_1 ...")
        sys.exit(1)
    client = _get_client()
    result = client.send_request("query.verify", {"expected_ids": args.ids})
    status = result.get("status", "?")
    found = result.get("found", [])
    missing = result.get("missing", [])
    orphans = result.get("orphans", [])
    print(f"Status: {status}")
    print(f"Found:  {len(found)}/{len(args.ids)}")
    if missing:
        print(f"MISSING: {', '.join(missing)}")
    if orphans:
        print(f"Orphans: {', '.join(orphans)}")
    client.disconnect()
    sys.exit(0 if status == "clean" else 1)


def cmd_capture(args):
    """Capture a view."""
    preset = args.preset or "iso"
    client = _get_client()
    params = {"preset": preset, "resolution": args.resolution or "med"}
    if args.save_dir:
        params["save_dir"] = args.save_dir
    else:
        from su_mcp_bridge.core.project import get_active_project

        project = get_active_project()
        if project:
            params["project_captures_dir"] = str(project.captures_dir)
    result = client.send_request("view.capture", params)
    if isinstance(result, dict) and result.get("error"):
        print(f"ERROR: {result['error']}")
        sys.exit(1)
    print(f"Captured {preset}: {result.get('path', '?')}")
    client.disconnect()


def cmd_capture_all(args):
    """Capture all 6 canonical views."""
    client = _get_client()
    params = {"resolution": args.resolution or "med"}
    if args.save_dir:
        params["save_dir"] = args.save_dir
    else:
        from su_mcp_bridge.core.project import get_active_project

        project = get_active_project()
        if project:
            params["project_captures_dir"] = str(project.captures_dir)
    result = client.send_request("view.capture_canonical", params)
    captures = result.get("captures", [])
    for c in captures:
        if isinstance(c, dict):
            print(f"  {c.get('preset', '?'):8s}  {c.get('path', '?')}")
    print(f"\n{len(captures)} views captured to {result.get('save_dir', '?')}")
    client.disconnect()


def cmd_agent(args):
    """Start the AI agent."""
    provider = (args.provider or "anthropic").lower()

    if provider == "ollama":
        from su_mcp_bridge.api_agent.ollama_agent import OllamaAgent

        model = args.model or "qwen2.5:7b"
        print(f"Using Ollama ({model}) — no API key needed")
        agent = OllamaAgent(model=model, verbose=True)
    else:
        from su_mcp_bridge.api_agent.agent import BuilderAgent

        try:
            agent = BuilderAgent(
                model=args.model or "claude-sonnet-4-20250514",
                verbose=True,
            )
        except OSError as e:
            print(f"ERROR: {e}")
            print("Tip: Use --provider ollama to use a local model instead.")
            sys.exit(1)

    if args.prompt:
        # Single-shot mode
        prompt = " ".join(args.prompt)
        agent.chat(prompt)
        agent.disconnect()
    else:
        # Interactive REPL
        label = f"Ollama/{args.model or 'qwen2.5:7b'}" if provider == "ollama" else "Claude"
        print(f"SketchUp AI Agent [{label}] (type 'quit' to exit)")
        print("-" * 40)
        try:
            while True:
                try:
                    user_input = input("\nYou> ").strip()
                except EOFError:
                    break
                if not user_input:
                    continue
                if user_input.lower() in ("quit", "exit", "q"):
                    break
                if user_input.lower() == "reset":
                    agent.reset()
                    print("[agent] Conversation reset.")
                    continue
                agent.chat(user_input)
        except KeyboardInterrupt:
            print("\n[agent] Interrupted.")
        finally:
            agent.disconnect()
            print("[agent] Disconnected.")


def cmd_mcp(_args):
    """Start the MCP server."""
    from su_mcp_bridge.mcp_server.server import mcp

    print("Starting MCP server (stdio)...", file=sys.stderr)
    mcp.run(transport="stdio")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sb",
        description="SketchUp Builder CLI — control SketchUp from the terminal",
    )
    sub = parser.add_subparsers(dest="command")

    # ping
    sub.add_parser("ping", help="Test bridge connectivity")

    # status
    sub.add_parser("status", help="Bridge status + scene summary")

    # clear
    sub.add_parser("clear", help="Clear the SketchUp model")

    # summary
    sub.add_parser("summary", help="Scene summary (token-efficient)")

    # verify
    p_verify = sub.add_parser("verify", help="Verify entity IDs exist")
    p_verify.add_argument("ids", nargs="*", help="Entity ai_ids to verify")

    # capture
    p_cap = sub.add_parser("capture", help="Capture a view")
    p_cap.add_argument(
        "preset",
        nargs="?",
        default="iso",
        choices=["plan", "iso", "elev_n", "elev_e", "elev_s", "elev_w"],
    )
    p_cap.add_argument("--resolution", "-r", default="med", choices=["low", "med", "high"])
    p_cap.add_argument("--save-dir", "-d", default="")

    # capture-all
    p_capall = sub.add_parser("capture-all", help="Capture all 6 canonical views")
    p_capall.add_argument("--resolution", "-r", default="med", choices=["low", "med", "high"])
    p_capall.add_argument("--save-dir", "-d", default="")

    # agent
    p_agent = sub.add_parser("agent", help="Start the AI agent")
    p_agent.add_argument("prompt", nargs="*", help="Prompt (omit for interactive REPL)")
    p_agent.add_argument("--model", "-m", default=None)
    p_agent.add_argument(
        "--provider",
        "-p",
        default="anthropic",
        choices=["anthropic", "ollama"],
        help="LLM provider (default: anthropic, use ollama for local)",
    )

    # mcp
    sub.add_parser("mcp", help="Start the MCP server (stdio)")

    # scan
    sub.add_parser("scan", help="Deep scan the model (full introspection)")

    # report
    p_report = sub.add_parser("report", help="Generate a model report")
    p_report.add_argument("--format", "-f", default="md", choices=["md", "csv", "json"])
    p_report.add_argument("--output", "-o", default="", help="Output directory")

    # save
    p_save = sub.add_parser("save", help="Save the model")
    p_save.add_argument("path", nargs="?", default="", help="Optional save path")

    # new
    sub.add_parser("new", help="Create a new SketchUp file")

    # open
    p_open = sub.add_parser("open", help="Open a .skp file")
    p_open.add_argument("path", help="Path to .skp file")

    # clash
    sub.add_parser("clash", help="Run clash detection")

    # project
    p_proj = sub.add_parser("project", help="Project management")
    p_proj.add_argument("action", choices=["create", "list", "open", "info"])
    p_proj.add_argument("name", nargs="*", help="Project name")

    # model-info
    sub.add_parser("model-info", help="Get model info")

    # walkthrough
    p_walk = sub.add_parser("walkthrough", help="Generate a walkthrough video")
    p_walk.add_argument(
        "preset", nargs="?", default="orbit", choices=["orbit", "flythrough", "cinematic"]
    )
    p_walk.add_argument("--frames", type=int, default=120)
    p_walk.add_argument("--fps", type=int, default=30)
    p_walk.add_argument("--resolution", "-r", default="med", choices=["low", "med", "high"])
    p_walk.add_argument("--save-dir", "-d", default="")

    # render
    p_rend = sub.add_parser("render", help="Capture a high-quality render (ultra resolution)")
    p_rend.add_argument(
        "preset",
        nargs="?",
        default="iso",
        choices=["plan", "iso", "elev_n", "elev_e", "elev_s", "elev_w"],
    )
    p_rend.add_argument("--save-dir", "-d", default="")
    p_rend.add_argument(
        "--style",
        "-s",
        choices=[
            "default",
            "hidden_line",
            "wireframe",
            "shaded",
            "shaded_tex",
            "monochrome",
            "xray",
        ],
        help="Apply a SketchUp rendering style",
    )

    # sketchup lifecycle
    p_su = sub.add_parser("sketchup", help="SketchUp lifecycle (start/stop/restart)")
    p_su.add_argument("action", choices=["start", "stop", "restart"])
    p_su.add_argument("--file", "-f", default="", help=".skp file to open on start")

    # house
    p_house = sub.add_parser("house", help="Generate a house from a prompt or config")
    p_house.add_argument(
        "prompt", nargs="*", help="Natural language description (uses AI to parse)"
    )
    p_house.add_argument("--bedrooms", "-b", type=int, default=None, help="Number of bedrooms")
    p_house.add_argument("--bathrooms", type=int, default=None)
    p_house.add_argument("--garage", action="store_true", default=False)
    p_house.add_argument("--roof", choices=["hip", "gable", "flat", "shed"], default=None)
    p_house.add_argument("--style", choices=["modern", "classic", "minimal"], default=None)
    p_house.add_argument(
        "--model", "-m", default="gemma4:e2b", help="Ollama model for prompt parsing"
    )
    p_house.add_argument(
        "--render", action="store_true", default=False, help="Take ISO render after building"
    )

    # undo
    sub.add_parser("undo", help="Trigger SketchUp undo")

    return parser


def cmd_scan(_args):
    """Deep scan the model."""
    client = _get_client()
    result = client.send_request("query.deep_scan")
    summary = result.get("summary", {})
    entities = result.get("entities", [])
    result.get("definitions", [])

    print("Deep Scan Complete")
    print(f"  Entities:    {summary.get('total_entities', 0)}")
    print(f"  Faces:       {summary.get('total_faces', 0)}")
    print(f"  Edges:       {summary.get('total_edges', 0)}")
    print(f"  Solids:      {summary.get('solids_count', 0)}")
    print(f"  Non-Solids:  {summary.get('non_solids_count', 0)}")
    print(f"  Definitions: {summary.get('definitions_count', 0)}")
    print()

    if entities:
        print(f"  {'AI ID':<20s} {'Type':<12s} {'Layer':<10s} {'Material':<15s} {'Solid':<6s}")
        print(f"  {'-' * 20} {'-' * 12} {'-' * 10} {'-' * 15} {'-' * 6}")
        for e in entities:
            solid = "Yes" if e.get("is_solid") else "No"
            print(
                f"  {e.get('ai_id', '?'):<20s} {e.get('type', '?'):<12s} {e.get('layer', '-'):<10s} {e.get('material', '-') or '-':<15s} {solid:<6s}"
            )
    client.disconnect()


def cmd_report(args):
    """Generate a report."""
    fmt = args.format or "md"
    client = _get_client()
    scan_data = client.send_request("query.deep_scan")
    client.disconnect()

    from su_mcp_bridge.core.report import (
        generate_csv_inventory,
        generate_json_snapshot,
        generate_model_report,
    )

    if fmt == "csv":
        path = generate_csv_inventory(scan_data, args.output or "")
    elif fmt == "json":
        path = generate_json_snapshot(scan_data, args.output or "")
    else:
        path = generate_model_report(scan_data, args.output or "")
    print(f"Report generated: {path}")


def cmd_save(args):
    """Save the model."""
    client = _get_client()
    params = {}
    if args.path:
        params["path"] = args.path
    else:
        from su_mcp_bridge.core.project import get_active_project

        project = get_active_project()
        if project:
            auto_path = str(project.model_dir / f"{project.name.replace(' ', '_')}.skp")
            params["path"] = auto_path
    result = client.send_request("lifecycle.save", params)
    print(f"Save: {result.get('status', '?')} -> {result.get('path', '?')}")
    client.disconnect()


def cmd_new(_args):
    """Create a new file."""
    client = _get_client()
    result = client.send_request("lifecycle.new")
    print(f"New file: {result.get('status', '?')}")
    client.disconnect()


def cmd_open(args):
    """Open a file."""
    client = _get_client()
    result = client.send_request("lifecycle.open", {"path": args.path})
    print(f"Open: {result.get('status', '?')} -> {result.get('path', '?')}")
    client.disconnect()


def cmd_clash(_args):
    """Run clash detection."""
    client = _get_client()
    result = client.send_request("query.clash_detect", {"tolerance_mm": 1.0})
    client.disconnect()

    clashes = result.get("clashes", [])
    total = result.get("total", 0)
    checked = result.get("entities_checked", 0)
    print(f"Clash Detection: {total} clashes found ({checked} entities checked)")
    if clashes:
        for c in clashes:
            sev = c.get("severity", "?").upper()
            print(f"  [{sev}] {c['entity_a']} ({c['type_a']}) <-> {c['entity_b']} ({c['type_b']})")
    else:
        print("  Model is clean!")


def cmd_project(args):
    """Project management."""
    from su_mcp_bridge.core.project import (
        create_project,
        get_active_project,
        list_projects,
        open_project,
    )

    action = args.action
    if action == "create":
        if not args.name:
            print("Usage: sb project create <name>")
            sys.exit(1)
        ctx = create_project(" ".join(args.name))
        print(f"Project created: {ctx.root}")
    elif action == "list":
        projects = list_projects()
        if not projects:
            print("No projects found.")
        else:
            for p in projects:
                print(f"  {p['name']:<30s} {p.get('created', '')[:10]}")
    elif action == "open":
        if not args.name:
            print("Usage: sb project open <name>")
            sys.exit(1)
        ctx = open_project(" ".join(args.name))
        if ctx:
            print(f"Project opened: {ctx.root}")
        else:
            print(f"Project not found: {' '.join(args.name)}")
    elif action == "info":
        ctx = get_active_project()
        if ctx:
            print(f"Active project: {ctx.name}")
            print(f"  Root: {ctx.root}")
            print(f"  Created: {ctx.created}")
        else:
            print("No active project.")
    else:
        print("Usage: sb project [create|list|open|info] [name]")


def cmd_model_info(_args):
    """Get model info."""
    client = _get_client()
    result = client.send_request("lifecycle.model_info")
    client.disconnect()
    for k, v in result.items():
        print(f"  {k:<25s} {v}")


def cmd_walkthrough(args):
    """Generate a walkthrough video."""
    preset = args.preset or "orbit"
    client = _get_client()
    params = {
        "preset": preset,
        "frames": args.frames,
        "fps": args.fps,
        "resolution": args.resolution or "med",
    }
    if args.save_dir:
        params["save_dir"] = args.save_dir
    else:
        from su_mcp_bridge.core.project import get_active_project

        project = get_active_project()
        if project:
            import os

            # Use project assets dir, but append /walkthrough/preset
            save_dir = os.path.join(str(project.assets_dir), f"walkthrough_{preset}")
            os.makedirs(save_dir, exist_ok=True)
            params["save_dir"] = save_dir

    print(f"Generating {preset} walkthrough ({args.frames} frames)...")
    result = client.send_request("view.walkthrough", params)
    client.disconnect()
    if result.get("error"):
        print(f"ERROR: {result['error']}")
    else:
        print(f"Walkthrough complete: {result.get('save_dir', '?')}")
        if result.get("mp4"):
            print(f"Video: {result['mp4']}")
        else:
            print("Frames saved (no FFmpeg found for MP4 stitching)")


def cmd_render(args):
    """Capture a high-quality render."""
    preset = args.preset or "iso"
    client = _get_client()
    params = {"preset": preset, "resolution": "ultra"}
    if args.style:
        params["style"] = args.style
    if args.save_dir:
        params["save_dir"] = args.save_dir
    else:
        from su_mcp_bridge.core.project import get_active_project

        project = get_active_project()
        if project:
            params["project_assets_dir"] = str(project.assets_dir)
    print(f"Capturing ultra-HQ {preset} render (3840x2880) with style {args.style or 'default'}...")
    result = client.send_request("view.capture", params)
    client.disconnect()
    if result.get("error"):
        print(f"ERROR: {result['error']}")
    else:
        print(f"Render saved: {result.get('path', '?')}")


def cmd_sketchup(args):
    """SketchUp lifecycle management."""
    from su_mcp_bridge.core.lifecycle import close_sketchup, restart_sketchup, start_sketchup

    action = args.action
    if action == "start":
        filepath = args.file or ""
        print("Starting SketchUp...")
        proc = start_sketchup(filepath, wait_for_bridge=True, timeout=30)
        if proc:
            print(f"SketchUp started (PID {proc.pid})")
        else:
            print("Failed to start SketchUp (executable not found)")
    elif action == "stop":
        print("Stopping SketchUp...")
        result = close_sketchup()
        print(f"Result: {result.get('status', '?')}")
    elif action == "restart":
        filepath = args.file or ""
        print("Restarting SketchUp...")
        result = restart_sketchup(filepath, timeout=30)
        print(f"Close: {result.get('close_result', {}).get('status', '?')}")
        print(f"Restarted: {result.get('restarted', False)}")


def cmd_undo(_args):
    """Trigger SketchUp undo."""
    client = _get_client()
    # SketchUp Undo via send_action
    client.send_request("lifecycle.model_info")  # Verify connection first
    # Use Sketchup.send_action via a simple eval
    try:
        client.send_request("eval", {"code": "Sketchup.send_action('editUndo:')"})
        print("Undo triggered")
    except Exception:
        print("Undo: sent (no confirmation available)")
    client.disconnect()


def cmd_house(args):
    """Generate a house from natural language or direct config."""
    config = {}

    # If direct flags are provided, use them
    if args.bedrooms is not None:
        config["bedrooms"] = args.bedrooms
    if args.bathrooms is not None:
        config["bathrooms"] = args.bathrooms
    if args.garage:
        config["has_garage"] = True
    if args.roof:
        config["roof_kind"] = args.roof
    if args.style:
        config["style"] = args.style

    # If a prompt is provided (and no direct flags), use Ollama to parse intent
    if args.prompt and not config:
        prompt_text = " ".join(args.prompt)
        print(f'Parsing: "{prompt_text}"')
        print(f"Using {args.model} for intent parsing...")
        config = _parse_house_prompt(prompt_text, args.model)
        print(f"Parsed config: {json.dumps(config, indent=2)}")
    elif not config:
        # Default: 2 bedroom house
        config = {"bedrooms": 2}

    # Build
    client = _get_client()
    from su_mcp_bridge.core.house_generator import HouseGenerator

    gen = HouseGenerator(client)
    gen.build(config)

    # Optional render
    if args.render:
        print("Taking ISO render...")
        params = {"preset": "iso", "resolution": "high"}
        from su_mcp_bridge.core.project import get_active_project

        project = get_active_project()
        if project:
            params["project_assets_dir"] = str(project.assets_dir)
        render_result = client.send_request("view.capture", params)
        print(f"Render saved: {render_result.get('path', '?')}")

    client.disconnect()


def _parse_house_prompt(prompt: str, model: str) -> dict:
    """Use a small Ollama model to extract house config from natural language."""
    try:
        from openai import OpenAI

        ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        client = OpenAI(base_url=f"{ollama_host}/v1", api_key="ollama")

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract house parameters from the user's description. "
                        "Return ONLY a JSON object with these optional keys: "
                        "bedrooms (int 1-5), bathrooms (int 1-3), "
                        "has_garage (bool), has_porch (bool), "
                        "roof_kind (hip/gable/flat/shed), "
                        "style (modern/classic/minimal). "
                        "Return ONLY valid JSON, no markdown, no explanation."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )

        text = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        return json.loads(text)
    except Exception as e:
        print(f"  [warning] AI parsing failed ({e}), using defaults")
        return {"bedrooms": 2}


DISPATCH = {
    "ping": cmd_ping,
    "status": cmd_status,
    "clear": cmd_clear,
    "summary": cmd_summary,
    "verify": cmd_verify,
    "capture": cmd_capture,
    "capture-all": cmd_capture_all,
    "agent": cmd_agent,
    "mcp": cmd_mcp,
    "scan": cmd_scan,
    "report": cmd_report,
    "save": cmd_save,
    "new": cmd_new,
    "open": cmd_open,
    "clash": cmd_clash,
    "project": cmd_project,
    "model-info": cmd_model_info,
    "walkthrough": cmd_walkthrough,
    "render": cmd_render,
    "sketchup": cmd_sketchup,
    "undo": cmd_undo,
    "house": cmd_house,
}


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    handler = DISPATCH.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
