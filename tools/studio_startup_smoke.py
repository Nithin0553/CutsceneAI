"""Live localhost Studio startup smoke without Unity, Unreal or model calls.

Launches the actual backend from a selected full checkout or extracted source
bundle using the selected Python interpreter. A temporary workspace prevents
changes to source projects, previous Studio runs and native job receipts.
This proves only the host/HTTP/UI bootstrap, NEVER rendered engine fidelity.
"""
from __future__ import annotations

import argparse
import json
import threading
from collections import deque
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import build_studio_bundle as distribution


class SmokeError(ValueError):
    pass


def _fetch(url: str, *, method: str = "GET", headers=None, body=None) -> tuple[int, bytes]:
    request = Request(url, data=body, method=method, headers=headers or {})
    try:
        with urlopen(request, timeout=2) as response:
            return response.status, response.read(512 * 1024)
    except HTTPError as exc:
        return exc.code, exc.read(512 * 1024)


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run(repo: Path, *, python: str = sys.executable,
        timeout_seconds: float = 40.0,
        source_bundle: Path | None = None) -> dict:
    root = Path(repo)
    if (root.is_symlink() or not root.is_dir()
            or not (root / "tools/studio_local_bridge.py").is_file()
            or not (root / "apps/studio-web/index.html").is_file()):
        raise SmokeError("Select a complete, non-symlink Studio source distribution.")
    root = root.resolve()
    source_sha = None
    source_manifest_sha = None
    portable_source_sha = None
    if source_bundle is not None:
        try:
            verified = distribution.verify_exact_checkout(root, Path(source_bundle))
        except (OSError, ValueError) as exc:
            raise SmokeError("Packaged Studio ZIP does not match extracted source.") from exc
        source_sha = verified["sha256"]
        source_manifest_sha = verified["source_manifest_sha256"]
        portable_source_sha = verified["portable_source_manifest_sha256"]
    if not 2 <= timeout_seconds <= 120:
        raise SmokeError("Smoke timeout must be between 2 and 120 seconds.")
    with tempfile.TemporaryDirectory(prefix="cutsceneai-startup-") as temp:
        workspace = Path(temp) / "runs"
        port = _free_local_port()
        url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        # This checks host bootstrap only and never sends a model request.
        env["CUTSCENEAI_MODEL_PROVIDER"] = "ollama"
        # Never place a subprocess stdout log inside a TemporaryDirectory:
        # Windows cannot unlink startup.log while another process still owns
        # the inherited OS file handle (WinError 32). A bounded pipe reader
        # retains a small diagnostic tail without leaving any on-disk log.
        process = None
        output_tail = deque(maxlen=64)
        drain_thread = None

        def drain_stdout():
            stream = process.stdout
            if stream is None:
                return
            try:
                for line in iter(stream.readline, b""):
                    output_tail.append(line.decode("utf-8", errors="replace")[-2048:])
            except (OSError, ValueError):
                pass

        def output_excerpt():
            return "".join(output_tail)[-1400:]

        try:
            process = subprocess.Popen(
                [python, str(root / "tools/studio_local_bridge.py"),
                 "--repo", str(root),
                 "--web", str(root / "apps/studio-web"),
                 "--workspace", str(workspace),
                 "--port", str(port)],
                cwd=root, env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            drain_thread = threading.Thread(
                target=drain_stdout,
                name="studio-smoke-output-drain",
                daemon=True,
            )
            drain_thread.start()
            deadline = time.monotonic() + timeout_seconds
            status = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise SmokeError(
                        "Studio exited before the localhost health check: "
                        + output_excerpt()
                    )
                try:
                    code, raw = _fetch(url + "/api/status")
                    if code == 200:
                        status = json.loads(raw)
                        break
                except (URLError, TimeoutError, ConnectionError, ValueError):
                    pass
                time.sleep(0.2)
            if status is None:
                raise SmokeError(
                    "Studio local server did not become healthy: "
                    + output_excerpt()
                )
            if status.get("connected") is not False:
                raise SmokeError("Isolated smoke workspace falsely has a source connection.")
            if not isinstance(status.get("token"), str) or len(status["token"]) < 16:
                raise SmokeError("Localhost session token is missing.")
            page_code, page = _fetch(url + "/")
            if page_code != 200 or b"CutSceneAI" not in page:
                raise SmokeError("Studio browser entrypoint is unavailable.")
            js_code, js = _fetch(url + "/cinematic.js")
            if js_code != 200 or len(js) < 2048:
                raise SmokeError("The standard Studio browser bundle is missing.")
            report_code, report_raw = _fetch(url + "/api/release-readiness")
            report = json.loads(report_raw)
            if report_code != 200 or report.get("release_ready") is not False:
                raise SmokeError("Fresh Studio workspace falsely claims release readiness.")
            flow_code, flow_raw = _fetch(url + "/api/flow-diagnostics")
            flow = json.loads(flow_raw)
            if (flow_code != 200
                    or flow.get("native_replay_authorized") is not False
                    or flow.get("source_and_native_full_fidelity_verified") is not False):
                raise SmokeError("Fresh workflow diagnostics authorized native replay.")
            post_code, _ = _fetch(
                url + "/api/connect", method="POST", body=b"{}",
                headers={"Content-Type": "application/json"},
            )
            if post_code != 403:
                raise SmokeError("Local session token was not required for mutations.")
            hostile_code, _ = _fetch(
                url + "/api/status",headers={"Host": "untrusted.example"},
            )
            if hostile_code != 403:
                raise SmokeError("Studio HTTP service accepted a foreign Host.")
            if any(workspace.glob("active-job.json")) or any(workspace.glob("jobs/*.json")):
                raise SmokeError("Startup smoke unexpectedly queued a native job.")
            result = {
                "kind": "cutsceneai.studio.phase10_5.localhost_startup_smoke",
                "status": "LIVE_LOCALHOST_AND_UI_SMOKE_PASSED_ENGINE_UNVERIFIED",
                "checks": {
                    "actual_server_process_started": "PASS",
                    "isolated_workspace_no_source": "PASS",
                    "session_token_required": "PASS",
                    "html_and_js_available": "PASS",
                    "source_bound_workflow_diagnostics": "PASS",
                    "no_forged_release_readiness": "PASS",
                    "foreign_host_rejected": "PASS",
                    "no_native_job_created": "PASS",
                },
                "source_distribution_sha256": source_sha,
                "source_manifest_sha256": source_manifest_sha,
                "portable_source_manifest_sha256": portable_source_sha,
                "native_editor_started": False,
                "unity_editor_started": False,
                "model_invoked": False,
                "full_cutscene_fidelity_verified": False,
                "production_release_ready": False,
            }
            return result
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=6)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=6)
                if drain_thread is not None:
                    drain_thread.join(timeout=2)
                # Do not wait indefinitely for grandchildren that inherited
                # stdout. They cannot lock a temp log because no file exists.
                if (process.stdout is not None
                        and (drain_thread is None or not drain_thread.is_alive())):
                    process.stdout.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--python", default=sys.executable,
                        help="Python with the Studio agent dependencies installed")
    parser.add_argument("--timeout", type=float, default=40.0)
    parser.add_argument("--source-bundle", type=Path,
                        help="Verify exact source ZIP contents against extracted Studio before startup")
    parser.add_argument("--output", type=Path,
                        help="Save an exclusive read-only smoke report outside repo")
    args = parser.parse_args(argv)
    try:
        result = run(args.repo, python=args.python, timeout_seconds=args.timeout,
                     source_bundle=args.source_bundle)
        if args.output:
            dest = args.output
            if dest.is_symlink() or dest.exists():
                raise SmokeError("Refusing to overwrite a prior Studio startup receipt.")
            if dest.resolve().is_relative_to(args.repo.resolve()):
                raise SmokeError("Startup receipt must be outside the source distribution.")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, sort_keys=True, indent=2)
                stream.write("\n")
    except (SmokeError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
