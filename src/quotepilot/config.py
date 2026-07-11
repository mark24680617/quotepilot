"""Central configuration: environment, model routing, business rules."""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

# --- Qwen Cloud (OpenAI-compatible) ---
QWEN_BASE_URL = os.getenv(
    "QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
)
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")

# Model routing: planner does the high-stakes bilingual drafting,
# worker handles extraction/classification, coder handles strict JSON mapping.
PLANNER_MODEL = os.getenv("QWEN_PLANNER_MODEL", "qwen-max")
WORKER_MODEL = os.getenv("QWEN_WORKER_MODEL", "qwen-flash")
CODER_MODEL = os.getenv("QWEN_CODER_MODEL", "qwen3-coder-plus")

# --- Paths ---
DATA_DIR = PROJECT_ROOT / "data"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
# On Alibaba Cloud Function Compute only /tmp is writable — override there.
RUNS_DIR = Path(os.getenv("QP_RUNS_DIR", PROJECT_ROOT / "runs"))

# Company-specific identity, terms, rules and catalog live in the
# CompanyProfile (see profile.py / data/company_profile.json), not here.
FALLBACK_USD_CNY = Decimal("7.15")  # offline fallback rate, labeled as indicative
