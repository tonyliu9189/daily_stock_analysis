"""Offline safety checks using disposable Git repositories; never touches GitHub refs."""

import json
from pathlib import Path
import subprocess

import pytest

from scripts import upstream_update as update


@pytest.fixture
def repository(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    local = tmp_path / "repo"
    local.mkdir()
    monkeypatch.chdir(local)
    update.git("init", "-b", "main")
    update.git("config", "user.name", "Offline test")
    update.git("config", "user.email", "test@example.invalid")
    Path("base.txt").write_text("base\n")
    update.git("add", ".")
    update.git("commit", "-m", "base")
    base = update.git("rev-parse", "HEAD")
    update.git("remote", "add", "origin", str(remote))
    update.git("push", "origin", "main")
    update.git("checkout", "-b", "upstream")
    Path("upstream.txt").write_text("new release\n")
    update.git("add", ".")
    update.git("commit", "-m", "release")
    upstream = update.git("rev-parse", "HEAD")
    update.git("checkout", "main")
    update.git("merge", "--no-ff", "--no-edit", upstream)
    candidate = update.git("rev-parse", "HEAD")
    directory = tmp_path / "artifact"
    directory.mkdir()
    update.git("update-ref", "refs/heads/upstream-candidate", candidate)
    update.git("bundle", "create", str(directory / "candidate.bundle"), "upstream-candidate")
    metadata = dict(repository="owner/fork", parent="author/source", tag="v1.2.3",
                    branch="main", base=base, candidate=candidate, upstream=upstream)
    (directory / "candidate.json").write_text(json.dumps(metadata))
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/fork")
    for key in ("base", "candidate", "upstream"):
        monkeypatch.setenv(f"EXPECTED_{key.upper()}", metadata[key])
    monkeypatch.setattr(update, "api", lambda path: {"default_branch": "main"})
    return directory, metadata


@pytest.mark.parametrize("value", ["v1.2.3-rc1", "../main", "v1.2.3\nattack", "--all"])
def test_release_input_rejects_non_stable_or_options(value):
    with pytest.raises(ValueError):
        update.valid_release(value)


def test_candidate_bundle_matches_trusted_prepare_outputs(repository):
    directory, metadata = repository
    assert update.validate_bundle(directory) == metadata


def test_rehearsal_never_changes_main_or_creates_backup(repository):
    directory, metadata = repository
    update.promote(directory, rehearsal=True)
    assert update.git("ls-remote", "origin", "refs/heads/main").split()[0] == metadata["base"]
    assert not update.git("ls-remote", "origin", "refs/heads/upstream-backups/*")


def test_missing_write_token_keeps_main_unchanged(repository, monkeypatch):
    directory, metadata = repository
    monkeypatch.delenv("GH_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="Missing GH_TOKEN"):
        update.promote(directory, rehearsal=False)
    assert update.git("ls-remote", "origin", "refs/heads/main").split()[0] == metadata["base"]
    assert not update.git("ls-remote", "origin", "refs/heads/upstream-backups/*")


def test_atomic_publication_retains_exact_previous_version(repository, monkeypatch):
    directory, metadata = repository
    monkeypatch.setenv("GH_TOKEN", "offline-test-placeholder")
    update.promote(directory, rehearsal=False)
    assert update.git("ls-remote", "origin", "refs/heads/main").split()[0] == metadata["candidate"]
    backup = f'refs/heads/upstream-backups/{metadata["base"]}'
    assert update.git("ls-remote", "origin", backup).split()[0] == metadata["base"]


def test_changed_main_ref_stops_publication(repository, monkeypatch):
    directory, metadata = repository
    Path("concurrent.txt").write_text("another commit\n")
    update.git("add", ".")
    update.git("commit", "-m", "concurrent main")
    changed = update.git("rev-parse", "HEAD")
    update.git("push", "origin", "main")
    monkeypatch.setenv("GH_TOKEN", "offline-test-placeholder")
    with pytest.raises(RuntimeError, match="Main changed"):
        update.promote(directory, rehearsal=False)
    assert update.git("ls-remote", "origin", "refs/heads/main").split()[0] == changed
    assert not update.git("ls-remote", "origin", "refs/heads/upstream-backups/*")


def test_artifact_cannot_replace_candidate_sha(repository):
    directory, metadata = repository
    metadata["candidate"] = metadata["base"]
    (directory / "candidate.json").write_text(json.dumps(metadata))
    with pytest.raises(RuntimeError, match="differs from trusted"):
        update.validate_bundle(directory)


def test_server_side_lease_blocks_main_change_after_last_read(repository, monkeypatch):
    directory, metadata = repository
    original_git = update.git
    def racing_git(*args):
        if args[:2] == ("push", "--atomic"):
            # This intervening version is an ancestor of candidate: plain push would accept it.
            original_git("push", "origin", f'{metadata["upstream"]}:refs/heads/main')
        return original_git(*args)
    monkeypatch.setenv("GH_TOKEN", "offline-test-placeholder")
    monkeypatch.setattr(update, "git", racing_git)
    with pytest.raises(subprocess.CalledProcessError):
        update.promote(directory, rehearsal=False)
    assert original_git("ls-remote", "origin", "refs/heads/main").split()[0] == metadata["upstream"]
    assert not original_git("ls-remote", "origin", "refs/heads/upstream-backups/*")


def test_foreign_artifact_rejected(repository):
    directory, metadata = repository
    metadata["repository"] = "other/repo"
    (directory / "candidate.json").write_text(json.dumps(metadata))
    with pytest.raises(RuntimeError, match="another repository"):
        update.validate_bundle(directory)


def test_non_merge_candidate_rejected(repository):
    _, metadata = repository
    with pytest.raises(RuntimeError, match="exact tested merge"):
        update.verify_candidate(metadata["base"], metadata["upstream"], metadata["upstream"])


def test_protected_file_change_requires_manual_review(repository):
    _, metadata = repository
    update.git("checkout", "upstream")
    Path("AGENTS.md").write_text("changed rules\n")
    update.git("add", ".")
    update.git("commit", "-m", "change protected file")
    upstream = update.git("rev-parse", "HEAD")
    update.git("checkout", "-b", "second-candidate", metadata["base"])
    update.git("merge", "--no-ff", "--no-edit", upstream)
    candidate = update.git("rev-parse", "HEAD")
    with pytest.raises(RuntimeError, match="Protected fork files changed"):
        update.verify_candidate(metadata["base"], candidate, upstream)


def test_shared_custom_code_dependencies_and_test_settings_are_protected(repository):
    _, metadata = repository
    paths = (
        'src/core/pipeline.py', 'src/share_image.py', 'src/notification_sender/email_sender.py',
        'src/market_analyzer.py', 'src/config.py', 'src/core/trading_calendar.py',
        '.github/requirements-ci.txt', 'requirements.txt', 'tests/conftest.py', 'setup.cfg', '.env',
        'tests/nested/conftest.py',
    )
    update.git('checkout', 'upstream')
    for name in paths:
        path = Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('changed\n')
    update.git('add', '.')
    update.git('commit', '-m', 'change protected load chain')
    upstream = update.git('rev-parse', 'HEAD')
    update.git('checkout', '-b', 'config-candidate', metadata['base'])
    update.git('merge', '--no-ff', '--no-edit', upstream)
    candidate = update.git('rev-parse', 'HEAD')
    with pytest.raises(RuntimeError) as caught:
        update.verify_candidate(metadata['base'], candidate, upstream)
    for name in paths:
        assert name in str(caught.value)


@pytest.mark.parametrize('xml', [
    '<testsuites/>',
    '<testsuite><testcase classname="tests.test_tw_market_review"><skipped/></testcase></testsuite>',
    '<testsuite><testcase classname="tests.test_tw_market_review"><failure/></testcase></testsuite>',
    '<testsuite><testcase classname="tests.test_tw_market_review"/></testsuite>',
])
def test_junit_rejects_collection_only_skipped_failed_or_missing_modules(tmp_path, xml):
    path = tmp_path / 'result.xml'
    path.write_text(xml)
    with pytest.raises(RuntimeError):
        update.verify_junit(path)


def test_junit_requires_executed_cases_in_each_mandatory_module(tmp_path):
    path = tmp_path / 'result.xml'
    cases = ''.join(f'<testcase classname="tests.{module}.TestCase"/>'
                    for module in update.REQUIRED_TEST_MODULES)
    path.write_text(f'<testsuite>{cases}</testsuite>')
    update.verify_junit(path)


@pytest.mark.parametrize('name', [
    'tests/測試/conftest.py', 'scripts/測試/sitecustomize.py',
    'tests/tab\tdirectory/conftest.py', 'tests/new\nline/conftest.py',
])
def test_load_chain_paths_use_nul_framing_without_git_quoting(monkeypatch, name):
    base, upstream, candidate = 'a' * 40, 'b' * 40, 'c' * 40
    monkeypatch.setattr(update, 'git', lambda *args: f'{base} {upstream}')
    def output(args):
        assert '-z' in args
        return b'' if args.index('--') < len(args) - 1 else name.encode('utf-8') + b'\0'
    monkeypatch.setattr(update.subprocess, 'check_output', output)
    with pytest.raises(RuntimeError, match='Protected fork files changed'):
        update.verify_candidate(base, candidate, upstream)


def test_telegram_failure_never_discloses_token(monkeypatch):
    for key, value in dict(TELEGRAM_BOT_TOKEN="private-placeholder", TELEGRAM_CHAT_ID="1",
                           GITHUB_REPOSITORY="owner/fork", GITHUB_RUN_ID="123",
                           PREPARE_RESULT="failure", TEST_RESULT="skipped",
                           PUBLISH_RESULT="skipped").items():
        monkeypatch.setenv(key, value)
    def fail(*args, **kwargs):
        raise OSError("https://api.telegram.org/botprivate-placeholder/sendMessage")
    monkeypatch.setattr(update.urllib.request, "urlopen", fail)
    with pytest.raises(RuntimeError) as caught:
        update.notify()
    assert "private-placeholder" not in str(caught.value)


def test_telegram_success_posts_only_update_status(monkeypatch):
    import io
    for key, value in dict(TELEGRAM_BOT_TOKEN="offline-placeholder", TELEGRAM_CHAT_ID="1",
                           GITHUB_REPOSITORY="owner/fork", GITHUB_RUN_ID="123",
                           PREPARE_RESULT="success", TEST_RESULT="success",
                           PUBLISH_RESULT="success", REHEARSAL="true").items():
        monkeypatch.setenv(key, value)
    sent = []
    def accept(request, timeout):
        sent.append(update.urllib.parse.parse_qs(request.data.decode()))
        return io.BytesIO(b'{"ok": true}')
    monkeypatch.setattr(update.urllib.request, "urlopen", accept)
    update.notify()
    assert len(sent) == 1
    assert "演練通過" in sent[0]["text"][0]
    assert "正式版本未變更" in sent[0]["text"][0]
    assert sent[0]["text"][0].endswith("https://github.com/owner/fork/actions/runs/123")


def test_prepare_rejects_incomplete_history_before_any_merge(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/fork")
    monkeypatch.setattr(update, "api", lambda path: (
        {"fork": True, "parent": {"full_name": "author/source"}} if path.endswith("owner/fork")
        else {"tag_name": "v1.2.3"}))
    calls = []
    def shallow_git(*args):
        calls.append(args)
        assert args == ("rev-parse", "--is-shallow-repository")
        return "true"
    monkeypatch.setattr(update, "git", shallow_git)
    with pytest.raises(RuntimeError, match="complete Git history"):
        update.prepare(tmp_path / "artifact")
    assert len(calls) == 1


def test_workflow_separates_testing_from_write_and_notification_secrets():
    import yaml
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/upstream-update.yml").read_text(encoding="utf-8"))
    assert workflow["permissions"] == {"contents": "read"}
    for name in ("prepare", "test"):
        assert "secrets." not in json.dumps(workflow["jobs"][name])
    assert workflow["jobs"]["publish"]["needs"] == ["prepare", "test"]
    assert workflow["jobs"]["publish"]["permissions"] == {"contents": "write"}
    assert "needs.test.result == 'success'" in workflow["jobs"]["publish"]["if"]
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] is False
                assert step["with"]["ref"] == "${{ github.sha }}"
