"""Prepare, verify and publish an upstream release without exposing test jobs to secrets."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


# Changes here require human review, even if Git could merge them automatically.
PROTECTED = (
    "AGENTS.md", "CLAUDE.md", ".github", ".env", ".env.example", ".env.*",
    "requirements*.txt", "setup.cfg", "pyproject.toml", "pytest.ini", "tox.ini",
    "conftest.py", "tests/conftest.py", "sitecustomize.py", "usercustomize.py",
    "scripts/upstream_update.py", "scripts/upstream_offline_checks.sh",
    "scripts/check_ai_assets.py", "scripts/ci_gate.sh", "scripts/ci_test_shard.py",
    "tests/test_upstream_update.py", "tests/test_taiwan_infographic.py",
    "tests/test_tw_market_review.py", "tests/test_tw_market_stats.py",
    "tests/test_infographic_delivery.py", "tests/test_pipeline_notification_image_routing.py",
    "tests/test_share_image.py", "tests/test_notification_sender.py",
    "data_provider/taiwan_market.py", "data_provider/taiwan_market_stats.py",
    "data_provider/base.py", "src/taiwan_infographic.py", "docs/taiwan-infographics.md",
    "src/core/pipeline.py", "src/share_image.py", "src/notification.py",
    "src/notification_sender", "src/market_analyzer.py", "src/config.py",
    "src/core/trading_calendar.py", "src/core/market_profile.py", "src/core/market_strategy.py",
    "src/core/market_review.py", "src/core/config_registry.py", "src/data/stock_mapping.py",
    "src/services/daily_market_context.py", "src/stock_code_utils.py",
)
REQUIRED_TEST_MODULES = (
    "test_tw_market_review", "test_tw_market_stats", "test_taiwan_infographic",
    "test_share_image", "test_infographic_delivery", "test_pipeline_notification_image_routing",
    "test_notification_sender", "test_upstream_update",
)
def run(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True, encoding="utf-8",
                                   stderr=subprocess.PIPE).strip()


def git(*args: str) -> str:
    return run("git", *args)


def valid_repo(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("Invalid repository identifier")
    return value


def valid_sha(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("Invalid commit SHA")
    return value


def valid_release(value: str) -> str:
    if not re.fullmatch(r"v?\d+\.\d+\.\d+", value):
        raise ValueError("Only stable semantic-version release tags are supported")
    return value


def api(path: str) -> dict:
    return json.loads(run("gh", "api", path))


def is_ancestor(ancestor: str, descendant: str) -> bool:
    result = subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, descendant],
                            capture_output=True)
    if result.returncode not in (0, 1):
        raise RuntimeError("Cannot verify commit ancestry")
    return result.returncode == 0


def verify_candidate(base: str, candidate: str, upstream: str) -> None:
    for sha in (base, candidate, upstream):
        valid_sha(sha)
    parents = git("show", "-s", "--format=%P", candidate).split()
    if parents != [base, upstream]:
        raise RuntimeError("Candidate must be the exact tested merge of base and release")
    changed = changed_paths(base, candidate, *PROTECTED)
    extra_hooks = [path for path in changed_paths(base, candidate)
                   if Path(path).name in {"conftest.py", "sitecustomize.py", "usercustomize.py"}]
    changed = list(dict.fromkeys(changed + extra_hooks))
    if changed:
        raise RuntimeError("Protected fork files changed; manual review required: "
                           + json.dumps(changed, ensure_ascii=True))


def changed_paths(base: str, candidate: str, *paths: str) -> list[str]:
    # NUL framing avoids Git's quoting and filenames containing tabs or newlines.
    raw = subprocess.check_output(["git", "diff", "--name-only", "-z", base, candidate, "--", *paths])
    return [path.decode("utf-8", errors="surrogateescape") for path in raw.split(b"\0") if path]


def prepare(output: Path) -> None:
    repo = valid_repo(os.environ["GITHUB_REPOSITORY"])
    info = api(f"repos/{repo}")
    if not info.get("fork") or not info.get("parent"):
        raise RuntimeError("Automatic updates require a verified parent fork repository")
    parent = valid_repo(info["parent"]["full_name"])
    release = api(f"repos/{parent}/releases/latest")
    if release.get("draft") or release.get("prerelease"):
        raise RuntimeError("Only published stable releases are accepted")
    tag = valid_release(release["tag_name"])
    if git("rev-parse", "--is-shallow-repository") != "false":
        raise RuntimeError("Prepare requires complete Git history (checkout fetch-depth: 0)")
    base = valid_sha(git("rev-parse", "HEAD"))
    if git("status", "--porcelain"):
        raise RuntimeError("Prepare requires a clean checkout")
    git("fetch", "--no-tags", f"https://github.com/{parent}.git", f"refs/tags/{tag}")
    upstream = valid_sha(git("rev-parse", "FETCH_HEAD^{commit}"))
    if is_ancestor(upstream, base):
        print("Latest stable release is already included; no update and no notification.")
        return
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "github-actions[bot]@users.noreply.github.com")
    git("merge", "--no-ff", "--no-edit", upstream)
    candidate = valid_sha(git("rev-parse", "HEAD"))
    verify_candidate(base, candidate, upstream)
    output.mkdir(parents=True, exist_ok=True)
    metadata = dict(repository=repo, parent=parent, tag=tag, base=base,
                    candidate=candidate, upstream=upstream, branch=info["default_branch"])
    git("update-ref", "refs/heads/upstream-candidate", candidate)
    git("bundle", "create", str((output / "candidate.bundle").resolve()), "upstream-candidate")
    (output / "candidate.json").write_text(json.dumps(metadata), encoding="utf-8")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
        for key in ("base", "candidate", "upstream", "tag"):
            handle.write(f"{key}={metadata[key]}\n")
        handle.write("ready=true\n")


def validate_bundle(directory: Path) -> dict:
    metadata = json.loads((directory / "candidate.json").read_text(encoding="utf-8"))
    repo = valid_repo(os.environ["GITHUB_REPOSITORY"])
    if metadata["repository"] != repo:
        raise RuntimeError("Candidate belongs to another repository")
    for key in ("base", "candidate", "upstream"):
        valid_sha(metadata[key])
        if metadata[key] != os.environ[f"EXPECTED_{key.upper()}"]:
            raise RuntimeError(f"Candidate {key} differs from trusted prepare output")
    valid_release(metadata["tag"])
    git("fetch", str((directory / "candidate.bundle").resolve()), "upstream-candidate")
    if git("rev-parse", "FETCH_HEAD") != metadata["candidate"]:
        raise RuntimeError("Bundle does not contain the expected candidate")
    verify_candidate(metadata["base"], metadata["candidate"], metadata["upstream"])
    return metadata


def promote(directory: Path, rehearsal: bool) -> None:
    metadata = validate_bundle(directory)
    repo = metadata["repository"]
    info = api(f"repos/{repo}")
    if info["default_branch"] != metadata["branch"]:
        raise RuntimeError("Default branch changed since preparation")
    branch = info["default_branch"]
    git("check-ref-format", f"refs/heads/{branch}")
    remote = git("ls-remote", "origin", f"refs/heads/{branch}").split()
    if not remote or remote[0] != metadata["base"]:
        raise RuntimeError("Main changed during testing; keep current version and retry next run")
    if rehearsal:
        print("Rehearsal passed: candidate verified; no remote refs were written.")
        return
    if not os.environ.get("GH_TOKEN"):
        raise RuntimeError("Missing GH_TOKEN; no backup or main ref was written")
    # The explicit lease is a server-side compare-and-swap, not permission to rewrite history:
    # verify_candidate requires base as first parent. Any different remote main makes this fail.
    git("push", "--atomic", "origin",
        f'--force-with-lease=refs/heads/{branch}:{metadata["base"]}',
        f'{metadata["base"]}:refs/heads/upstream-backups/{metadata["base"]}',
        f'{metadata["candidate"]}:refs/heads/{branch}')
    actual = git("ls-remote", "origin", f"refs/heads/{branch}").split()[0]
    if actual != metadata["candidate"]:
        raise RuntimeError("Remote verification failed after push; inspect run before retry")
    print("Backup and tested update published; remote SHA verified.")


def verify_junit(path: Path) -> None:
    cases = list(ET.parse(path).getroot().iter("testcase"))
    executed = [case for case in cases if case.find("skipped") is None]
    if not executed or any(case.find("failure") is not None or case.find("error") is not None
                           for case in cases):
        raise RuntimeError("Tests were not executed successfully")
    for module in REQUIRED_TEST_MODULES:
        if not any(module in case.get("classname", "").split(".") for case in executed):
            raise RuntimeError(f"Mandatory fork tests did not execute: {module}")
    print("Mandatory fork tests actually executed; JUnit result verified.")


def notify() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise RuntimeError("Telegram credentials missing; inspect Actions result")
    statuses = {key: os.environ[key] for key in ("PREPARE_RESULT", "TEST_RESULT", "PUBLISH_RESULT")}
    rehearsal = os.environ.get("REHEARSAL") == "true"
    if all(value == "success" for value in statuses.values()):
        message = "自動更新演練通過，正式版本未變更。" if rehearsal else "自動更新完成，已建立舊版備份並核對遠端版本。"
    else:
        message = "自動更新未完成，請查看紀錄。若更新步驟尚未成功，正式版本維持原狀。"
    repo = valid_repo(os.environ["GITHUB_REPOSITORY"])
    run_id = os.environ["GITHUB_RUN_ID"]
    if not run_id.isdecimal():
        raise ValueError("Invalid run ID")
    text = f"{message}\n準備／測試／更新：{' / '.join(statuses.values())}\nhttps://github.com/{repo}/actions/runs/{run_id}"
    body = urllib.parse.urlencode(dict(chat_id=chat_id, text=text)).encode()
    request = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.load(response)
        if not result.get("ok"):
            raise ValueError("Telegram rejected message")
    except Exception:
        # Request URLs contain the bot token; never print the underlying exception.
        raise RuntimeError("Telegram notification failed; inspect Actions result") from None
    print("Telegram notification accepted.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "validate", "promote", "verify-junit", "notify"))
    parser.add_argument("--directory", type=Path, default=Path("candidate-artifact"))
    parser.add_argument("--rehearsal", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            prepare(args.directory)
        elif args.action == "validate":
            validate_bundle(args.directory)
        elif args.action == "promote":
            promote(args.directory, args.rehearsal)
        elif args.action == "verify-junit":
            verify_junit(args.directory)
        else:
            notify()
    except subprocess.CalledProcessError as error:
        # Git credential helpers and API errors may contain credentials. Keep command output private.
        print(f"Update stopped: external command failed (exit {error.returncode}); remote publication not confirmed.", file=sys.stderr)
        sys.exit(1)
    except (RuntimeError, ValueError, KeyError, OSError) as error:
        print(f"Update stopped: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
