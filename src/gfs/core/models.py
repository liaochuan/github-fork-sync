from pydantic import BaseModel


class RepoInfo(BaseModel):
    full_name: str
    default_branch: str
    parent_full_name: str
    parent_default_branch: str
    html_url: str


class CommitInfo(BaseModel):
    sha: str
    message: str
    author: str
    date: str
    html_url: str


class DiffResult(BaseModel):
    repo: RepoInfo
    status: str
    behind_by: int
    ahead_by: int
    behind_commits: list[CommitInfo]
    ahead_commits: list[CommitInfo]
    error_message: str | None = None


class SyncResult(BaseModel):
    repo_full_name: str
    success: bool
    merge_type: str | None = None
    message: str
    error_code: str | None = None


class SkippedRepo(BaseModel):
    full_name: str
    reason: str
