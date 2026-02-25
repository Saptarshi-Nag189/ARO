"""
ARO Configuration Module
========================
Central configuration for the Autonomous Research Operator.
All configurable parameters are defined here.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class ModelConfig:
    """Configuration for a specific model assignment."""
    model_id: str = "arcee-ai/trinity-large-preview:free"
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class AROConfig:
    """Master configuration for the ARO system."""

    # --- Global Mode ---
    mode: str = "production"  # options: "production", "audit"

    # --- API Configuration ---
    openrouter_api_key: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_API_KEY", "")
    )
    openrouter_base_url: str = "https://openrouter.ai/api/v1/chat/completions"

    # --- Model Assignments (per agent) ---
    default_model: str = "arcee-ai/trinity-large-preview:free"

    agent_models: Dict[str, ModelConfig] = field(default_factory=lambda: {
        "planner":          ModelConfig(temperature=0.5),
        "research":         ModelConfig(temperature=0.7),
        "claim_extraction": ModelConfig(temperature=0.3, max_tokens=8192),
        "skeptic":          ModelConfig(temperature=0.6, max_tokens=8192),
        "synthesis":        ModelConfig(temperature=0.6, max_tokens=8192),
        "innovation":       ModelConfig(temperature=0.8),
        "reflection":       ModelConfig(temperature=0.5),
        "orchestrator":     ModelConfig(temperature=0.4),
    })

    # --- Iteration & Budget Limits ---
    min_iterations: int = 3
    max_iterations: int = 10
    max_docs_per_iteration: int = 5
    max_tokens_per_call: int = 4096
    budget_cap_usd: float = 5.0

    # --- Mathematical Constants ---
    epsilon: float = 1e-8
    risk_floor: float = 0.08

    # --- Termination Thresholds ---
    risk_threshold: float = 0.25
    novelty_plateau_delta: float = 0.03
    novelty_plateau_window: int = 3
    stale_iteration_window: int = 2

    # --- Database ---
    db_path: str = "aro_memory.db"

    # --- Logging ---
    log_dir: str = "logs"

    # --- Gateway Retries ---
    max_retries: int = 3

    def get_model_config(self, agent_name: str) -> ModelConfig:
        """Get model configuration for a specific agent."""
        return self.agent_models.get(agent_name, ModelConfig())


# Singleton instance
config = AROConfig()
