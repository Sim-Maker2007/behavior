"""
Swarm configuration — loads from YAML and environment variables.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None


@dataclass
class OpenVikingConfig:
    """Configuration for the OpenViking context layer."""
    mode: str = "local"  # "local" or "remote"
    workspace_path: str = "./viking_workspace"
    server_url: str = "http://localhost:1933"
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-large"
    vlm_provider: str = "litellm"
    vlm_model: str = "claude-sonnet-4-20250514"


@dataclass
class MiroFishConfig:
    """Configuration for the MiroFish simulation engine."""
    backend_url: str = "http://localhost:5001"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model_name: str = "gpt-4o"
    zep_api_key: str = ""
    max_simulation_agents: int = 100
    simulation_steps: int = 50


@dataclass
class SwarmConfig:
    """Top-level swarm configuration."""
    openviking: OpenVikingConfig = field(default_factory=OpenVikingConfig)
    mirofish: MiroFishConfig = field(default_factory=MiroFishConfig)
    cards_directory: str = "./cards"
    behavior_selection: str = "auto"  # "auto", "manual", or list of card names
    selected_cards: list = field(default_factory=list)
    max_concurrent_agents: int = 10
    prediction_depth: str = "standard"  # "quick", "standard", "deep"
    output_format: str = "report"  # "report", "json", "interactive"

    @classmethod
    def from_yaml(cls, path: str) -> "SwarmConfig":
        if yaml is None:
            raise ImportError("PyYAML required: pip install pyyaml")
        with open(path) as f:
            raw = yaml.safe_load(f)
        return cls._from_dict(raw)

    @classmethod
    def from_env(cls) -> "SwarmConfig":
        """Build config from environment variables with sensible defaults."""
        cfg = cls()
        cfg.openviking.server_url = os.getenv("OPENVIKING_URL", cfg.openviking.server_url)
        cfg.openviking.workspace_path = os.getenv("OPENVIKING_WORKSPACE", cfg.openviking.workspace_path)
        cfg.openviking.embedding_provider = os.getenv("OPENVIKING_EMBED_PROVIDER", cfg.openviking.embedding_provider)
        cfg.mirofish.backend_url = os.getenv("MIROFISH_URL", cfg.mirofish.backend_url)
        cfg.mirofish.llm_api_key = os.getenv("LLM_API_KEY", cfg.mirofish.llm_api_key)
        cfg.mirofish.llm_base_url = os.getenv("LLM_BASE_URL", cfg.mirofish.llm_base_url)
        cfg.mirofish.llm_model_name = os.getenv("LLM_MODEL_NAME", cfg.mirofish.llm_model_name)
        cfg.mirofish.zep_api_key = os.getenv("ZEP_API_KEY", cfg.mirofish.zep_api_key)
        cfg.cards_directory = os.getenv("ABC_CARDS_DIR", cfg.cards_directory)
        return cfg

    @classmethod
    def _from_dict(cls, d: dict) -> "SwarmConfig":
        cfg = cls()
        if "openviking" in d:
            ov = d["openviking"]
            for k, v in ov.items():
                if hasattr(cfg.openviking, k):
                    setattr(cfg.openviking, k, v)
        if "mirofish" in d:
            mf = d["mirofish"]
            for k, v in mf.items():
                if hasattr(cfg.mirofish, k):
                    setattr(cfg.mirofish, k, v)
        for k in ["cards_directory", "behavior_selection", "selected_cards",
                   "max_concurrent_agents", "prediction_depth", "output_format"]:
            if k in d:
                setattr(cfg, k, d[k])
        return cfg
