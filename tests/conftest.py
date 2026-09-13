import os
import sys

# Tests never talk to W&B or model endpoints.
os.environ["WANDB_API_KEY"] = ""
os.environ["VARIANTCOURT_MODE"] = "demo"
os.environ["EVIDENCE_MODE"] = "fixtures"
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))
