"""Source identity for public GitHub workflow evidence; contains no credentials."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess


REPOSITORY = "Baharul0111/RingSight"
WORKFLOWS = ("keepalive.yml", "daily-probe.yml", "ci.yml")
SOURCE_FOLDERS = ("server", "seed", "synth", "tests", "ui/src", "evals")
SOURCE_SUFFIXES = {".py", ".cypher", ".jsx", ".js", ".tsx", ".ts", ".css"}
EXPLICIT_SOURCES = (
    "Dockerfile", "docker-compose.yml", "render.yaml", "pyproject.toml", "uv.lock",
    "ui/package.json", "ui/package-lock.json", "ops/daily_probe.py",
    "ops/cloudflare-worker.js", "ops/wrangler.toml", "ops/workflow_evidence.py",
    *(".github/workflows/" + name for name in WORKFLOWS))


def workflow_sources(root: Path) -> list[Path]:
    files = []
    for folder in SOURCE_FOLDERS:
        files.extend(path for path in (root / folder).rglob("*")
                     if path.is_file() and path.suffix in SOURCE_SUFFIXES)
    files.extend(root / name for name in EXPLICIT_SOURCES)
    return sorted({path for path in files if path.is_file()})


def workflow_source_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in workflow_sources(root):
        digest.update(str(path.relative_to(root)).encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def commit_matches_sources(root: Path, commit: str) -> bool:
    """Compare actual Git blobs, including deleted paths, without checking out."""
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
        return False
    tree = subprocess.run(["git", "ls-tree", "-rz", commit], cwd=root,
                          capture_output=True, check=False, timeout=15)
    if tree.returncode:
        return False
    committed = {}
    for entry in tree.stdout.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        name = raw_path.decode()
        is_source = name in EXPLICIT_SOURCES or (Path(name).suffix in SOURCE_SUFFIXES
                    and any(name.startswith(folder + "/") for folder in SOURCE_FOLDERS))
        if is_source:
            committed[name] = metadata.split()[2].decode()
    current = {str(path.relative_to(root)): path for path in workflow_sources(root)}
    if set(committed) != set(current):
        return False
    for name, path in current.items():
        data = path.read_bytes()
        algorithm = hashlib.sha256 if len(committed[name]) == 64 else hashlib.sha1
        if algorithm(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() != committed[name]:
            return False
    return True


def validate_workflow_evidence(value: dict, root: Path, workflows=WORKFLOWS) -> None:
    """Reject old source, another repository, or an unfinished/failed latest job.

    The source digest excludes generated docs/results. Committing the evidence
    therefore does not invalidate its source identity or create a hash cycle.
    """
    def require(condition, message):
        if not condition:
            raise AssertionError(message)
    require(value.get("status") == "passed", "Operational workflow collection did not pass.")
    require(value.get("repository") == REPOSITORY, "Operational evidence names another repository.")
    require(value.get("source_fingerprint") == workflow_source_fingerprint(root), "Operational jobs predate current runtime/tests/workflows.")
    head = value.get("head_sha")
    require(isinstance(head, str) and len(head) in {40, 64}, "Operational evidence has no source commit.")
    for name in workflows:
        run = value.get("workflows", {}).get(name, {})
        run_head = run.get("headSha")
        require(isinstance(run_head, str) and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", run_head), "Workflow has no source commit: " + name)
        require(run.get("source_fingerprint") == value["source_fingerprint"], "Workflow source fingerprint differs: " + name)
        require(run.get("status") == "completed" and run.get("conclusion") == "success", "No successful current-source run: " + name)
        require(isinstance(run.get("databaseId"), int) and run["databaseId"] > 0, "Missing workflow run id: " + name)
        require(run.get("url") == f"https://github.com/{REPOSITORY}/actions/runs/{run['databaseId']}", "Unexpected workflow run link: " + name)
