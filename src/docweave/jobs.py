"""A bounded, single-process queue with durable task metadata."""

import json
import os
import queue
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        # The Windows virtualenv launcher has a Python child; stop the whole tree.
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        process.kill()


class Jobs:
    # ponytail: one translation at a time; use a separate queue service for multiple servers.
    def __init__(self, root: Path, timeout=1800, retention=86400):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.server_lock = (self.root / "server.lock").open("a+b")
        if self.server_lock.tell() == 0:
            self.server_lock.write(b"0")
            self.server_lock.flush()
        self.server_lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.server_lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.server_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.server_lock.close()
            raise RuntimeError(
                "Thư mục dữ liệu đang được một DocWeave khác sử dụng. Chỉ chạy một máy chủ cho mỗi thư mục."
            ) from None
        self.timeout, self.retention = timeout, retention
        self.lock = threading.RLock()
        self.pending = queue.Queue(maxsize=8)
        self.stopping = threading.Event()
        self.process = None
        self.active_id = None
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, owner TEXT NOT NULL, created REAL NOT NULL, data TEXT NOT NULL)"
            )
            for row in db.execute("SELECT id, data FROM jobs").fetchall():
                data = json.loads(row[1])
                if data["status"] in ("queued", "running"):
                    data.update(
                        status="error",
                        stage="Tác vụ bị gián đoạn khi máy chủ khởi động lại. Hãy gửi lại tài liệu.",
                    )
                    db.execute(
                        "UPDATE jobs SET data=? WHERE id=?", (json.dumps(data), row[0])
                    )
        self.thread = threading.Thread(
            target=self.run, daemon=True, name="docweave-queue"
        )
        self.thread.start()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / "jobs.sqlite3", timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def list(self, owner):
        with self.lock, self.connect() as db:
            return [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT data FROM jobs WHERE owner=? ORDER BY created DESC LIMIT 50",
                    (owner,),
                )
            ]

    def get(self, job_id, owner=None):
        with self.lock, self.connect() as db:
            row = db.execute(
                "SELECT owner, data FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            return (
                json.loads(row[1])
                if row and (owner is None or row[0] == owner)
                else None
            )

    def update(self, job_id, **changes):
        with self.lock, self.connect() as db:
            data = self.get(job_id)
            if not data or data["status"] in ("cancelled", "done", "error"):
                return
            data.update(changes)
            db.execute(
                "UPDATE jobs SET data=? WHERE id=?",
                (json.dumps(data, ensure_ascii=False), job_id),
            )

    def submit(self, owner, filename, content, pages, options, credentials):
        with self.lock:
            if self.pending.full():
                raise queue.Full
            job_id = uuid.uuid4().hex
            folder = self.root / job_id
            folder.mkdir()
            data = dict(
                id=job_id,
                filename=filename,
                pages=pages,
                created=time.time(),
                status="queued",
                progress=0,
                stage="Đang chờ đến lượt",
                lang_in=options["lang_in"],
                lang_out=options["lang_out"],
            )
            try:
                (folder / "input.pdf").write_bytes(content)
                (folder / "options.json").write_text(
                    json.dumps(options), encoding="utf-8"
                )
                with self.connect() as db:
                    db.execute(
                        "INSERT INTO jobs VALUES (?, ?, ?, ?)",
                        (
                            job_id,
                            owner,
                            data["created"],
                            json.dumps(data, ensure_ascii=False),
                        ),
                    )
                self.pending.put_nowait((job_id, credentials))
            except Exception:
                with self.connect() as db:
                    db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
                shutil.rmtree(folder)
                raise
            return data

    def cancel(self, job_id):
        with self.lock:
            self.update(job_id, status="cancelled", stage="Đã hủy")
            if (
                self.active_id == job_id
                and self.process
                and self.process.poll() is None
            ):
                stop_process(self.process)

    def clean(self):
        with self.lock, self.connect() as db:
            for job_id, raw in db.execute(
                "SELECT id, data FROM jobs WHERE created < ?",
                (time.time() - self.retention,),
            ).fetchall():
                if json.loads(raw)["status"] not in ("queued", "running"):
                    folder = (self.root / job_id).resolve()
                    if folder.parent != self.root:
                        continue
                    shutil.rmtree(folder, ignore_errors=True)
                    db.execute("DELETE FROM jobs WHERE id=?", (job_id,))

    def run(self):
        last_clean = 0
        while not self.stopping.is_set():
            if time.time() - last_clean > 60:
                self.clean()
                last_clean = time.time()
            try:
                job_id, credentials = self.pending.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self.execute(job_id, credentials)
            except Exception:
                self.update(
                    job_id,
                    status="error",
                    stage="Không thể khởi chạy bộ xử lý. Kiểm tra môi trường máy chủ rồi thử lại.",
                )
            finally:
                credentials.clear()
                self.pending.task_done()

    def execute(self, job_id, credentials):
        folder = self.root / job_id
        timer = None
        expired = threading.Event()
        with self.lock:
            if self.get(job_id)["status"] != "queued" or self.stopping.is_set():
                return
            self.update(job_id, status="running", stage="Đang khởi động bộ xử lý PDF")
            env = os.environ.copy()
            env.update(credentials)
            env.update(
                PYTHONUTF8="1",
                PYTHONIOENCODING="utf-8",
                BABELDOC_CACHE_DIR=str(self.root / "runtime"),
            )
            self.active_id = job_id
            self.process = subprocess.Popen(
                [sys.executable, "-m", "docweave.worker", str(folder)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            process = self.process

        def timeout():
            if process.poll() is None:
                expired.set()
                stop_process(process)

        try:
            timer = threading.Timer(self.timeout, timeout)
            timer.start()
            for line in process.stdout:
                if not line.startswith("DOCWEAVE:"):
                    continue
                try:
                    event = json.loads(line[len("DOCWEAVE:") :])
                except ValueError:
                    continue
                if event.get("type") == "progress":
                    self.update(
                        job_id,
                        stage=event["stage"],
                        progress=max(0, min(99, float(event.get("progress", 0)))),
                    )
                elif event.get("type") == "error":
                    self.update(job_id, status="error", stage=event["message"])
            code = process.wait()
            if code == 0 and all(
                (folder / name).is_file()
                for name in ("translated.pdf", "bilingual.pdf")
            ):
                self.update(
                    job_id, status="done", stage="Tài liệu đã sẵn sàng", progress=100
                )
            else:
                message = (
                    "Tác vụ quá thời gian xử lý. Hãy thử tài liệu ít trang hơn."
                    if expired.is_set()
                    else "Bộ xử lý chưa tạo được kết quả. Kiểm tra kết nối tải model/font và cấu hình dịch vụ dịch."
                )
                self.update(job_id, status="error", stage=message)
        finally:
            if timer:
                timer.cancel()
            if process.poll() is None:
                stop_process(process)
            process.wait()
            process.stdout.close()
            with self.lock:
                self.process = None
                self.active_id = None

    def close(self):
        self.stopping.set()
        with self.lock:
            if self.process and self.process.poll() is None:
                stop_process(self.process)
        self.thread.join(timeout=10)
        while True:
            try:
                _, credentials = self.pending.get_nowait()
                credentials.clear()
                self.pending.task_done()
            except queue.Empty:
                break
        self.server_lock.close()
