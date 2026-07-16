"""场景用例规格。"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class PathSetCase:
    case_id: str
    description: str
    expected_paths: List[str]
    min_precision: float = 0.6
    min_recall: float = 0.6
    top_k: int = 8
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SymbolRelationCase:
    case_id: str
    description: str
    symbol: str
    expected_paths: List[str]
    min_precision: float = 0.5
    min_recall: float = 0.5
    limit: int = 30
