"""
Quick Weave connectivity test.
Run from the project root:
    python scripts/test_weave.py

This will:
  1. Load .env and authenticate with W&B
  2. Call weave.init() — creates the project if it doesn't exist
  3. Log one traced function call as a test trace
  4. Print the exact dashboard URL weave reports
"""
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load .env first
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import os
import weave

api_key = os.getenv("WANDB_API_KEY", "")
entity  = os.getenv("WANDB_ENTITY", "")
project = os.getenv("WANDB_PROJECT", "nexus")

print(f"WANDB_API_KEY : {'SET (' + api_key[:12] + '...)' if api_key else 'NOT SET'}")
print(f"WANDB_ENTITY  : {entity or 'NOT SET'}")
print(f"WANDB_PROJECT : {project}")
print()

if not api_key:
    print("ERROR: WANDB_API_KEY is not set in .env")
    sys.exit(1)

# Init — weave prints the URL itself
init_arg = f"{entity}/{project}" if entity else project
print(f"Calling weave.init('{init_arg}') ...")
client = weave.init(init_arg)
print()

# Log a test trace so the project page isn't empty
@weave.op()
def test_trace(message: str) -> str:
    return f"Oasia Weave connection OK — {message}"

result = test_trace("hello from nexus")
print(f"Test trace result: {result}")
print()
print("Done. Open the URL printed above by weave.init() to see your dashboard.")
