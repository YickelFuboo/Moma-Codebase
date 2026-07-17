from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class FileChange:
    path: str
    status: str
    additions: int = 0
    deletions: int = 0

    @property
    def churn(self) -> int:
        return int(self.additions) + int(self.deletions)


@dataclass
class GitHistoryEntry:
    commit_sha: str
    message: str
    committed_at: Optional[datetime]
    is_merge: bool
    files: List[FileChange] = field(default_factory=list)


@dataclass
class ExperienceStep:
    file: str
    action: str


@dataclass
class ExperiencePattern:
    title: str
    steps: List[ExperienceStep]
    source_commits: List[str]
    commit_message: str = ""
