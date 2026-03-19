"""Interview Prep GraphRAG configuration."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = (BASE_DIR / "../../data/C10").resolve()


@dataclass
class InterviewGraphRAGConfig:
    """Configuration for the interview preparation GraphRAG demo system."""

    data_dir: Path = DATA_DIR
    progress_store: Path = BASE_DIR / "study_progress.json"
    top_k_dense: int = 5
    top_k_keyword: int = 5
    top_k_final: int = 6
    graph_hops: int = 2
    review_interval_days: List[int] = field(default_factory=lambda: [1, 3, 7, 14, 30])
    supported_extensions: Dict[str, str] = field(
        default_factory=lambda: {
            ".md": "markdown",
            ".txt": "text",
            ".pdf": "pdf",
            ".png": "image",
            ".jpg": "image",
            ".jpeg": "image",
        }
    )


DEFAULT_CONFIG = InterviewGraphRAGConfig()
