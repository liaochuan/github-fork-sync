from gfs.core.models import RepoInfo, CommitInfo, DiffResult, SyncResult


def test_repo_info():
    r = RepoInfo(
        full_name="my-fork/project-a",
        default_branch="main",
        parent_full_name="original/project-a",
        parent_default_branch="main",
        html_url="https://github.com/my-fork/project-a",
    )
    assert r.full_name == "my-fork/project-a"
    assert r.parent_full_name == "original/project-a"


def test_commit_info():
    c = CommitInfo(
        sha="abc1234",
        message="feat: add feature",
        author="Alice",
        date="2026-08-15T10:00:00Z",
        html_url="https://github.com/o/r/commit/abc1234",
    )
    assert c.sha == "abc1234"
    assert c.author == "Alice"


def test_diff_result():
    d = DiffResult(
        repo=RepoInfo(
            full_name="my-fork/project-a",
            default_branch="main",
            parent_full_name="original/project-a",
            parent_default_branch="main",
            html_url="https://github.com/my-fork/project-a",
        ),
        status="behind",
        behind_by=3,
        ahead_by=0,
        behind_commits=[
            CommitInfo(
                sha="abc1234",
                message="feat: x",
                author="Alice",
                date="2026-08-15T10:00:00Z",
                html_url="https://github.com/o/r/commit/abc1234",
            )
        ],
        ahead_commits=[],
    )
    assert d.behind_by == 3
    assert len(d.behind_commits) == 1
    assert d.ahead_commits == []


def test_sync_result_success():
    s = SyncResult(
        repo_full_name="my-fork/project-a",
        success=True,
        merge_type="merge",
        message="Merged upstream into main",
        error_code=None,
    )
    assert s.success is True
    assert s.error_code is None


def test_sync_result_failure():
    s = SyncResult(
        repo_full_name="my-fork/project-a",
        success=False,
        merge_type=None,
        message="Merge conflict",
        error_code="409",
    )
    assert s.success is False
    assert s.error_code == "409"
