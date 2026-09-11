"""Web integration checks; the engine is simulated to avoid paid API requests."""

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pymupdf
from fastapi.testclient import TestClient

from docweave.app import create_app
from docweave.jobs import Jobs


def pdf_bytes(pages=1, encrypted=False):
    with pymupdf.open() as pdf:
        for _ in range(pages):
            pdf.new_page().insert_text((72, 72), "A document for integration testing.")
        return (
            pdf.tobytes(
                encryption=pymupdf.PDF_ENCRYPT_AES_256,
                owner_pw="owner",
                user_pw="reader",
            )
            if encrypted
            else pdf.tobytes()
        )


def wait_for(getter, statuses, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = getter()
        if result and result["status"] in statuses:
            return result
        time.sleep(0.05)
    raise AssertionError(f"Task did not reach {statuses}: {result}")


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "",
                "DOCWEAVE_ACCESS_TOKEN": "",
                "DOCWEAVE_ALLOWED_HOSTS": "testserver",
                "DOCWEAVE_MAX_PAGES": "2",
                "DOCWEAVE_MAX_UPLOAD_MB": "1",
                "PYTHON_DOTENV_DISABLED": "1",
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        # Exercise a real child process and the actual queue protocol, using a deterministic engine fixture.
        self.real_popen = subprocess.Popen
        self.script = 'import pathlib,sys; p=pathlib.Path(sys.argv[1]); data=(p/\'input.pdf\').read_bytes(); (p/\'translated.pdf\').write_bytes(data); (p/\'bilingual.pdf\').write_bytes(data); print(\'DOCWEAVE:{"type":"progress","stage":"Fixture","progress":70}\',flush=True)'
        self.launch = patch(
            "docweave.jobs.subprocess",
            SimpleNamespace(
                Popen=lambda args, **kwargs: self.real_popen(
                    [sys.executable, "-c", self.script, args[-1]], **kwargs
                ),
                PIPE=subprocess.PIPE,
                DEVNULL=subprocess.DEVNULL,
                CREATE_NO_WINDOW=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                run=subprocess.run,
            ),
        )
        self.launch.start()
        self.addCleanup(self.launch.stop)
        self.app = create_app(self.temp.name)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.client.get("/")

    def submit(self, **changes):
        data = {
            "lang_in": "en",
            "lang_out": "vi",
            "api_key": "fixture-secret-do-not-persist",
        }
        data.update(changes)
        return self.client.post(
            "/api/jobs",
            files={"file": ("tài liệu.pdf", pdf_bytes(), "application/pdf")},
            data=data,
            headers={"X-DocWeave": "1"},
        )

    def test_upload_progress_download_and_secret_not_persisted(self):
        response = self.submit()
        self.assertEqual(response.status_code, 202, response.text)
        job_id = response.json()["id"]
        result = wait_for(
            lambda: self.client.get("/api/jobs/" + job_id).json(), {"done", "error"}
        )
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["progress"], 100)
        for kind in ("translated", "bilingual"):
            result = self.client.get(f"/api/jobs/{job_id}/download/{kind}")
            self.assertEqual(result.status_code, 200)
            with pymupdf.open(stream=result.content, filetype="pdf") as pdf:
                self.assertEqual(len(pdf), 1)
        for path in Path(self.temp.name).rglob("*"):
            if path.is_file() and path.name != "server.lock":
                self.assertNotIn(b"fixture-secret-do-not-persist", path.read_bytes())

    def test_other_session_cannot_read_cancel_or_download(self):
        job_id = self.submit().json()["id"]
        other = TestClient(self.app)
        try:
            self.assertEqual(other.get("/api/jobs").json(), [])
            self.assertEqual(other.get("/api/jobs/" + job_id).status_code, 404)
            self.assertEqual(
                other.post(
                    "/api/jobs/" + job_id + "/cancel", headers={"X-DocWeave": "1"}
                ).status_code,
                404,
            )
            self.assertEqual(
                other.get("/api/jobs/" + job_id + "/download/translated").status_code,
                404,
            )
        finally:
            other.close()

    def test_validation_and_cross_origin(self):
        self.assertEqual(self.submit(api_key="").status_code, 400)
        self.assertEqual(self.submit(lang_out="en").status_code, 400)
        for content in (b"not a PDF", pdf_bytes(3), pdf_bytes(encrypted=True)):
            result = self.client.post(
                "/api/jobs",
                files={"file": ("test.pdf", content)},
                data={"api_key": "fixture"},
                headers={"X-DocWeave": "1"},
            )
            self.assertEqual(result.status_code, 400, result.text)
        self.assertEqual(self.client.post("/api/jobs").status_code, 403)
        self.assertEqual(
            self.client.post(
                "/api/jobs",
                headers={"X-DocWeave": "1", "Origin": "https://other.example"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/", headers={"Host": "other.example"}).status_code, 400
        )
        self.assertEqual(
            self.client.post(
                "/api/jobs",
                content=b"x" * (1024 * 1024 + 65537),
                headers={"X-DocWeave": "1"},
            ).status_code,
            413,
        )

    def test_cancel_stops_running_process(self):
        self.script = "import os,pathlib,sys,time; (pathlib.Path(sys.argv[1])/'worker.pid').write_text(str(os.getpid())); time.sleep(30)"
        job_id = self.submit().json()["id"]
        wait_for(lambda: self.app.state.jobs.get(job_id), {"running"})
        pid_file = Path(self.temp.name) / job_id / "worker.pid"
        deadline = time.monotonic() + 10
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(pid_file.exists())
        worker_pid = int(pid_file.read_text())
        result = self.client.post(
            "/api/jobs/" + job_id + "/cancel", headers={"X-DocWeave": "1"}
        )
        self.assertEqual(result.json()["status"], "cancelled")
        deadline = time.monotonic() + 5
        while self.app.state.jobs.process and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertIsNone(self.app.state.jobs.process)
        self.assertEqual(self.app.state.jobs.get(job_id)["status"], "cancelled")
        import psutil

        self.assertFalse(
            psutil.pid_exists(worker_pid), "Python worker survived cancellation"
        )

    def test_failure_and_timeout_do_not_report_success(self):
        self.script = "import sys; sys.exit(1)"
        job_id = self.submit().json()["id"]
        self.assertEqual(
            wait_for(lambda: self.app.state.jobs.get(job_id), {"done", "error"})[
                "status"
            ],
            "error",
        )
        self.app.state.jobs.timeout = 0.2
        self.script = "import time; time.sleep(30)"
        job_id = self.submit().json()["id"]
        result = wait_for(lambda: self.app.state.jobs.get(job_id), {"done", "error"})
        self.assertEqual(result["status"], "error")
        self.assertIn("quá thời gian", result["stage"])

    def test_expired_files_are_deleted(self):
        job_id = self.submit().json()["id"]
        wait_for(lambda: self.app.state.jobs.get(job_id), {"done"})
        self.app.state.jobs.retention = -1
        self.app.state.jobs.clean()
        self.assertEqual(self.client.get("/api/jobs/" + job_id).status_code, 404)
        self.assertFalse((Path(self.temp.name) / job_id).exists())

    def test_access_token_and_static_page(self):
        with patch.dict(os.environ, {"DOCWEAVE_ACCESS_TOKEN": "fixture-access"}):
            with (
                tempfile.TemporaryDirectory() as directory,
                TestClient(create_app(directory)) as client,
            ):
                self.assertEqual(client.get("/").status_code, 200)
                self.assertEqual(
                    client.get("/api/health").json()["auth_required"], True
                )
                self.assertEqual(client.get("/api/config").status_code, 401)
                result = client.get(
                    "/api/config", headers={"Authorization": "Bearer fixture-access"}
                )
                self.assertEqual(result.status_code, 200)
                self.assertNotIn("fixture-access", result.text)
                self.assertIn(
                    "frame-ancestors", result.headers["content-security-policy"]
                )

    def test_second_server_cannot_share_live_queue(self):
        with self.assertRaises(RuntimeError):
            Jobs(Path(self.temp.name))

    def test_restart_marks_interrupted_jobs(self):
        self.script = "import time; time.sleep(30)"
        job_id = self.submit().json()["id"]
        wait_for(lambda: self.app.state.jobs.get(job_id), {"running"})
        # Simulate persisted queued work left by an interrupted previous server.
        jobs = self.app.state.jobs
        jobs.close()
        with jobs.connect() as db:
            import json

            data = jobs.get(job_id)
            data["status"] = "queued"
            db.execute("UPDATE jobs SET data=? WHERE id=?", (json.dumps(data), job_id))
        restored = Jobs(Path(self.temp.name))
        try:
            self.assertEqual(restored.get(job_id)["status"], "error")
            self.assertIn("khởi động lại", restored.get(job_id)["stage"])
        finally:
            restored.close()


if __name__ == "__main__":
    unittest.main()
