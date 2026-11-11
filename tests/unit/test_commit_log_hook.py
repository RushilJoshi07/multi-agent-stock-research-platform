"""The commit-log hook (.claude/hooks/commit-log-note.sh), run for real against throwaway git
repos: one note file per commit, at docs/explanations/phase-N/commits/<short-sha>.md
(docs/decisions/0008).

The hook gets the same JSON on stdin that Claude Code sends after a Bash tool call. The repo root
comes from the input's `cwd`, so in a worktree session the file lands in the worktree. These tests
set CLAUDE_PROJECT_DIR to a different repo to prove the hook doesn't use it.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "commit-log-note.sh"


@pytest.fixture
def git_env(tmp_path: Path) -> dict[str, str]:
    """Isolate git from the user's global config (signing, hooks, templates)."""
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("[user]\n\tname = Hook Test\n\temail = hook@test.invalid\n")
    # Drop inherited GIT_* variables (GIT_DIR, GIT_WORK_TREE, ...), which would point git at
    # another repo, e.g. when pytest runs from inside a git hook.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return {**env, "GIT_CONFIG_GLOBAL": str(gitconfig), "GIT_CONFIG_NOSYSTEM": "1"}


def git(repo: Path, env: dict[str, str], *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], env=env, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def make_repo(path: Path, env: dict[str, str], phase: int = 1) -> Path:
    path.mkdir()
    git(path, env, "init", "-q", "-b", "main")
    (path / "docs").mkdir()
    (path / "docs" / "STATUS.md").write_text(f"# Status\n\n**Current phase:** {phase} — test\n")
    git(path, env, "add", ".")
    git(path, env, "commit", "-q", "-m", "Initial commit")
    return path


def commit_file(repo: Path, env: dict[str, str], rel: str, message: str) -> str:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{message}\n")
    git(repo, env, "add", rel)
    git(repo, env, "commit", "-q", "-m", message)
    return git(repo, env, "rev-parse", "--short", "HEAD")


def run_hook(
    cwd: Path | None, env: dict[str, str], command: str, project_dir: Path
) -> subprocess.CompletedProcess:
    payload = {
        "session_id": "test",
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
    if cwd is not None:
        payload["cwd"] = str(cwd)
    return subprocess.run(
        [str(HOOK)],
        input=json.dumps(payload),
        env={**env, "CLAUDE_PROJECT_DIR": str(project_dir)},
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )


def note_files(repo: Path) -> list[Path]:
    return sorted((repo / "docs" / "explanations").rglob("commits/*.md"))


@pytest.fixture
def decoy(tmp_path: Path, git_env: dict[str, str]) -> Path:
    """A different repo for CLAUDE_PROJECT_DIR; nothing may ever be written here."""
    return make_repo(tmp_path / "decoy", git_env)


def test_a_commit_gets_its_own_note_file(
    tmp_path: Path, git_env: dict[str, str], decoy: Path
) -> None:
    repo = make_repo(tmp_path / "repo", git_env)
    sha = commit_file(repo, git_env, "src/app.py", "Add the app")

    result = run_hook(repo, git_env, "git commit -m 'Add the app'", project_dir=decoy)

    note = repo / "docs" / "explanations" / "phase-1" / "commits" / f"{sha}.md"
    assert note_files(repo) == [note]
    text = note.read_text()
    assert text.startswith(f"# {sha} — Add the app\n")
    assert "_note pending_" in text
    assert "1 file changed" in text
    # Claude is told where to write the note.
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert str(note.relative_to(repo)) in context
    assert note_files(decoy) == []


def test_a_docs_only_commit_gets_no_file(
    tmp_path: Path, git_env: dict[str, str], decoy: Path
) -> None:
    repo = make_repo(tmp_path / "repo", git_env)
    commit_file(repo, git_env, "docs/explanations/phase-1/step-01-x.md", "Explainer")

    result = run_hook(repo, git_env, "git commit -m Explainer", project_dir=decoy)

    assert note_files(repo) == []
    assert result.stdout == ""


def test_a_second_run_on_the_same_commit_changes_nothing(
    tmp_path: Path, git_env: dict[str, str], decoy: Path
) -> None:
    repo = make_repo(tmp_path / "repo", git_env)
    commit_file(repo, git_env, "src/app.py", "Add the app")
    run_hook(repo, git_env, "git commit -m x", project_dir=decoy)
    [note] = note_files(repo)
    note.write_text(note.read_text().replace("_note pending_", "A real note."))

    result = run_hook(repo, git_env, "git commit -m x", project_dir=decoy)

    assert note_files(repo) == [note]
    assert "A real note." in note.read_text()
    assert result.stdout == ""


@pytest.mark.parametrize("command", ["git status", "git commit --dry-run -m x", "echo commit"])
def test_commands_that_are_not_commits_get_no_file(
    tmp_path: Path, git_env: dict[str, str], decoy: Path, command: str
) -> None:
    repo = make_repo(tmp_path / "repo", git_env)
    commit_file(repo, git_env, "src/app.py", "Add the app")

    run_hook(repo, git_env, command, project_dir=decoy)

    assert note_files(repo) == []


def test_a_commit_in_a_worktree_lands_in_the_worktree(
    tmp_path: Path, git_env: dict[str, str]
) -> None:
    main = make_repo(tmp_path / "main", git_env)
    worktree = tmp_path / "main" / ".claude" / "worktrees" / "pipeline-import"
    git(main, git_env, "worktree", "add", "-q", "-b", "pipeline-import", str(worktree))
    sha = commit_file(worktree, git_env, "src/pipeline.py", "Import the pipeline")

    # A worktree session's CLAUDE_PROJECT_DIR may be the main checkout; the cwd is the worktree.
    run_hook(worktree, git_env, "git commit -m 'Import the pipeline'", project_dir=main)

    assert note_files(worktree) == [
        worktree / "docs" / "explanations" / "phase-1" / "commits" / f"{sha}.md"
    ]
    assert [p for p in note_files(main) if not p.is_relative_to(worktree)] == []


def test_the_phase_comes_from_the_repos_own_status(
    tmp_path: Path, git_env: dict[str, str], decoy: Path
) -> None:
    repo = make_repo(tmp_path / "repo", git_env, phase=3)
    sha = commit_file(repo, git_env, "src/app.py", "Add the app")

    run_hook(repo, git_env, "git commit -m x", project_dir=decoy)

    assert note_files(repo) == [
        repo / "docs" / "explanations" / "phase-3" / "commits" / f"{sha}.md"
    ]


def test_a_cwd_outside_any_repo_is_ignored(
    tmp_path: Path, git_env: dict[str, str], decoy: Path
) -> None:
    outside = tmp_path / "not-a-repo"
    outside.mkdir()

    result = run_hook(outside, git_env, "git commit -m x", project_dir=decoy)

    assert result.stdout == ""
    assert note_files(decoy) == []


def test_a_cwd_in_a_subfolder_finds_the_repo_root(
    tmp_path: Path, git_env: dict[str, str], decoy: Path
) -> None:
    repo = make_repo(tmp_path / "repo", git_env)
    sha = commit_file(repo, git_env, "src/app.py", "Add the app")

    run_hook(repo / "src", git_env, "git commit -m x", project_dir=decoy)

    assert note_files(repo) == [
        repo / "docs" / "explanations" / "phase-1" / "commits" / f"{sha}.md"
    ]


def test_git_dash_c_uses_the_named_repo_not_the_cwd(
    tmp_path: Path, git_env: dict[str, str]
) -> None:
    """The main session committing in a worktree with `git -C <worktree> commit`."""
    main = make_repo(tmp_path / "main", git_env)
    worktree = tmp_path / "main" / ".claude" / "worktrees" / "pipeline-import"
    git(main, git_env, "worktree", "add", "-q", "-b", "pipeline-import", str(worktree))
    sha = commit_file(worktree, git_env, "src/pipeline.py", "Import the pipeline")

    run_hook(
        main,
        git_env,
        "git -C .claude/worktrees/pipeline-import commit -m 'Import the pipeline'",
        project_dir=main,
    )

    assert note_files(worktree) == [
        worktree / "docs" / "explanations" / "phase-1" / "commits" / f"{sha}.md"
    ]
    assert [p for p in note_files(main) if not p.is_relative_to(worktree)] == []


def test_a_commit_with_thousands_of_files_still_gets_a_note(
    tmp_path: Path, git_env: dict[str, str], decoy: Path
) -> None:
    """The file list is far bigger than a pipe buffer (64 KB). A grep that stops reading early
    must not make the hook skip the commit."""
    repo = make_repo(tmp_path / "repo", git_env)
    fixtures = repo / "tests" / "fixtures"
    fixtures.mkdir(parents=True)
    for i in range(3000):
        (fixtures / f"captured_response_number_{i:05d}_for_a_long_file_name.json").write_text("{}")
    git(repo, git_env, "add", ".")
    git(repo, git_env, "commit", "-q", "-m", "Add captured fixtures")
    sha = git(repo, git_env, "rev-parse", "--short", "HEAD")

    run_hook(repo, git_env, "git commit -m 'Add captured fixtures'", project_dir=decoy)

    assert note_files(repo) == [
        repo / "docs" / "explanations" / "phase-1" / "commits" / f"{sha}.md"
    ]


def test_a_missing_cwd_falls_back_to_the_project_dir(
    tmp_path: Path, git_env: dict[str, str]
) -> None:
    repo = make_repo(tmp_path / "repo", git_env)
    sha = commit_file(repo, git_env, "src/app.py", "Add the app")

    run_hook(None, git_env, "git commit -m x", project_dir=repo)

    assert note_files(repo) == [
        repo / "docs" / "explanations" / "phase-1" / "commits" / f"{sha}.md"
    ]


def test_a_subject_with_printf_and_quote_characters_is_written_as_is(
    tmp_path: Path, git_env: dict[str, str], decoy: Path
) -> None:
    repo = make_repo(tmp_path / "repo", git_env)
    subject = """Fix 100% of "quoted" 'cases' and a back\\slash %s %d"""
    sha = commit_file(repo, git_env, "src/app.py", subject)

    run_hook(repo, git_env, "git commit -F msg.txt", project_dir=decoy)

    [note] = note_files(repo)
    assert note.read_text().splitlines()[0] == f"# {sha} — {subject}"


def test_an_empty_commit_gets_no_file(tmp_path: Path, git_env: dict[str, str], decoy: Path) -> None:
    repo = make_repo(tmp_path / "repo", git_env)
    commit_file(repo, git_env, "src/app.py", "Add the app")
    git(repo, git_env, "commit", "-q", "--allow-empty", "-m", "Empty")

    result = run_hook(repo, git_env, "git commit --allow-empty -m Empty", project_dir=decoy)

    assert note_files(repo) == []
    assert result.stdout == ""


def test_a_merge_commit_gets_no_file(tmp_path: Path, git_env: dict[str, str], decoy: Path) -> None:
    """A --no-ff merge finished with `git commit` (e.g. after resolving a conflict)."""
    repo = make_repo(tmp_path / "repo", git_env)
    git(repo, git_env, "checkout", "-q", "-b", "feature")
    commit_file(repo, git_env, "src/feature.py", "Add the feature")
    git(repo, git_env, "checkout", "-q", "main")
    git(repo, git_env, "merge", "-q", "--no-ff", "--no-commit", "feature")
    git(repo, git_env, "commit", "-q", "-m", "Merge feature")

    result = run_hook(repo, git_env, "git commit -m 'Merge feature'", project_dir=decoy)

    assert note_files(repo) == []
    assert result.stdout == ""


@pytest.mark.parametrize(
    "command",
    [
        "git commit -F - <<'EOF'\nP2: run git -C wt commit from the main session\nEOF",
        "git commit -m 'Rule: use git -C wt commit in a worktree'",
    ],
    ids=["heredoc-body", "message-text"],
)
def test_git_dash_c_in_the_message_is_not_the_repo(
    tmp_path: Path, git_env: dict[str, str], decoy: Path, command: str
) -> None:
    repo = make_repo(tmp_path / "repo", git_env)
    sha = commit_file(repo, git_env, "src/app.py", "Add the app")

    run_hook(repo, git_env, command, project_dir=decoy)

    assert note_files(repo) == [
        repo / "docs" / "explanations" / "phase-1" / "commits" / f"{sha}.md"
    ]


def test_cd_then_commit_writes_no_stub_and_says_so(tmp_path: Path, git_env: dict[str, str]) -> None:
    """The hook can't know where `cd` took the shell, so it must not stub cwd's HEAD (the wrong
    commit); it tells the session to write that note by hand instead."""
    main = make_repo(tmp_path / "main", git_env)
    commit_file(main, git_env, "src/app.py", "Main's own commit")
    worktree = tmp_path / "main" / ".claude" / "worktrees" / "pipeline-import"
    git(main, git_env, "worktree", "add", "-q", "-b", "pipeline-import", str(worktree))
    commit_file(worktree, git_env, "src/pipeline.py", "Import the pipeline")

    result = run_hook(
        main, git_env, "cd .claude/worktrees/pipeline-import && git commit -m x", project_dir=main
    )

    assert note_files(main) == []
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "by hand" in context


def test_git_dash_c_with_a_home_path(tmp_path: Path, git_env: dict[str, str], decoy: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    repo = make_repo(home / "repo", git_env)
    sha = commit_file(repo, git_env, "src/app.py", "Add the app")

    run_hook(decoy, {**git_env, "HOME": str(home)}, "git -C ~/repo commit -m x", project_dir=decoy)

    assert note_files(repo) == [
        repo / "docs" / "explanations" / "phase-1" / "commits" / f"{sha}.md"
    ]


def test_dry_run_mentioned_in_the_message_is_still_a_real_commit(
    tmp_path: Path, git_env: dict[str, str], decoy: Path
) -> None:
    repo = make_repo(tmp_path / "repo", git_env)
    sha = commit_file(repo, git_env, "src/app.py", "Hook: skip --dry-run commits")

    run_hook(repo, git_env, "git commit -m 'Hook: skip --dry-run commits'", project_dir=decoy)

    assert note_files(repo) == [
        repo / "docs" / "explanations" / "phase-1" / "commits" / f"{sha}.md"
    ]
