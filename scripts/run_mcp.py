"""Launch one GigBid MCP server over stdio from anywhere (used by MCP hosts such as the Inspector,
Claude Desktop or Cursor):   python scripts/run_mcp.py portfolio|marketplace|workspace
"""
import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("GIGSIM_URL", "inprocess")
name = sys.argv[1] if len(sys.argv) > 1 else "portfolio"
sys.argv = [sys.argv[0]]
runpy.run_module(f"mcp_servers.{name}.server", run_name="__main__")
