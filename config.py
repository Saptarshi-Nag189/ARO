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


# ─── Model IDs ───────────────────────────────────────────────────────────────
# These are the OpenRouter model identifiers for free-tier models.
MODEL_TRINITY = "arcee-ai/trinity-large-preview:free"
MODEL_STEP    = "stepfun/step-3.5-flash:free"
MODEL_GPT_OSS = "openai/gpt-oss-120b:free"


@dataclass
class ModelConfig:
    """Configuration for a specific model assignment."""
    model_id: str = MODEL_TRINITY
    temperature: float = 0.7
    max_tokens: int = 4096
    enable_reasoning: bool = False  # Chain-of-thought reasoning (Step 3.5 Flash, GPT-OSS-120B)


@dataclass
class AROConfig:
    """Master configuration for the ARO system."""

    # --- Global Mode ---
    mode: str = "production"  # options: "production", "audit"

    # --- API Configuration ---
    # Per-model API keys (each model can have its own key)
    openrouter_api_key: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_API_KEY", "")
    )
    openrouter_api_key_step: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_API_KEY_STEP", "")
    )
    openrouter_api_key_gpt_oss: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_API_KEY_GPT_OSS", "")
    )
    openrouter_base_url: str = "https://openrouter.ai/api/v1/chat/completions"

    # --- Model Assignments (per agent) ---
    # Strategy: Step 3.5 Flash for structured output (planner, claim_extraction)
    #           GPT-OSS-120B for deep reasoning (skeptic, synthesis, reflection)
    #           Trinity Large Preview for creative + long context (research, innovation, orchestrator)
    default_model: str = MODEL_TRINITY

    agent_models: Dict[str, ModelConfig] = field(default_factory=lambda: {
        # ── Structured Output Agents → Step 3.5 Flash ──
        "planner":          ModelConfig(model_id=MODEL_STEP, temperature=0.5, enable_reasoning=True),
        "claim_extraction": ModelConfig(model_id=MODEL_STEP, temperature=0.3, max_tokens=8192, enable_reasoning=True),

        # ── Reasoning Agents → GPT-OSS-120B ──
        "skeptic":          ModelConfig(model_id=MODEL_GPT_OSS, temperature=0.6, max_tokens=8192, enable_reasoning=True),
        "synthesis":        ModelConfig(model_id=MODEL_GPT_OSS, temperature=0.6, max_tokens=8192, enable_reasoning=True),
        "reflection":       ModelConfig(model_id=MODEL_GPT_OSS, temperature=0.5, enable_reasoning=True),
        "fast_synthesis":   ModelConfig(model_id=MODEL_GPT_OSS, temperature=0.6, max_tokens=8192, enable_reasoning=True),

        # ── Creative / Long-Context Agents → Trinity Large Preview ──
        "research":         ModelConfig(model_id=MODEL_TRINITY, temperature=0.7),
        "innovation":       ModelConfig(model_id=MODEL_TRINITY, temperature=0.8),
        "orchestrator":     ModelConfig(model_id=MODEL_TRINITY, temperature=0.4),
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

    # --- Vector Store (Cross-Session Memory) ---
    vector_store_path: str = "vector_store"
    vector_search_top_k: int = 10
    enable_cross_session_memory: bool = True

    # --- Cache ---
    search_cache_ttl: int = 3600  # 1 hour TTL for search results
    enable_search_cache: bool = True

    # --- Fast Mode ---
    fast_mode_max_search_queries: int = 3
    fast_mode_model: str = MODEL_GPT_OSS

    def get_model_config(self, agent_name: str) -> ModelConfig:
        """Get model configuration for a specific agent."""
        return self.agent_models.get(agent_name, ModelConfig())

    def get_api_key_for_model(self, model_id: str) -> str:
        """
        Route the correct API key based on model ID.

        Each model provider may have a different API key on OpenRouter.
        Falls back to the default key if no specific key is configured.
        """
        if MODEL_STEP in model_id and self.openrouter_api_key_step:
            return self.openrouter_api_key_step
        if MODEL_GPT_OSS in model_id and self.openrouter_api_key_gpt_oss:
            return self.openrouter_api_key_gpt_oss
        # Default: Trinity / fallback
        return self.openrouter_api_key


# Singleton instance
config = AROConfig()
