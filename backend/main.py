import os
import sys
import json
import shutil
import sqlite3
import threading
import subprocess
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from database import get_db, init_db, DB_PATH
from models import SessionCreate, SessionUpdate, PhotoUpdate, ExportRequest
import scan_config as _cfg

app = FastAPI(title="Photo Library API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Scan jobs persisted to disk so they survive backend restarts
_scan_jobs: dict[str, dict] = {}
_JOBS_FILE = Path(__file__).parent / "jobs.json"
_jobs_lock = threading.Lock()


def _persist_jobs():
    with _jobs_lock:
        _JOBS_FILE.write_text(
            json.dumps(_scan_jobs, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _load_jobs():
    if not _JOBS_FILE.exists():
        return
    try:
        data = json.loads(_JOBS_FILE.read_text(encoding="utf-8"))
        for job_id, job in data.items():
            # Check if the subprocess is still alive
            pid = job.get("pid")
            if job.get("status") == "running" and pid:
                try:
                    os.kill(pid, 0)   # signal 0 = just check existence
                except OSError:
                    job["status"] = "error"
                    job["error"] = "Proces skončil (backend byl restartován)"
            _scan_jobs[job_id] = job
    except Exception:
        pass


@app.on_event("startup")
def startup():
    init_db()
    _load_jobs()


# ── helpers ───────────────────────────────────────────────────────────────────

def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def _photo_with_thumb_url(photo: dict, thumb_dir: str) -> dict:
    thumb_full = str(Path(thumb_dir) / photo["thumb"])
    photo["thumb_url"] = f"/api/thumb?path={quote(thumb_full)}"
    photo["dof"] = bool(photo["dof"])
    photo["best_in_group"] = bool(photo["best_in_group"])
    photo["selected"] = bool(photo["selected"])
    photo["exported"] = bool(photo["exported"])
    return photo


# ── Sessions ──────────────────────────────────────────────────────────────────

@app.get("/api/sessions")
def list_sessions():
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT s.*, COUNT(CASE WHEN p.selected=1 THEN 1 END) AS selected_count
            FROM sessions s
            LEFT JOIN photos p ON p.session_id = s.id
            GROUP BY s.id
            ORDER BY s.scanned_at DESC
        """).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


@app.post("/api/sessions", status_code=202)
def create_session(req: SessionCreate):
    import uuid
    job_id = str(uuid.uuid4())[:8]

    script = Path(__file__).parent.parent / "photo_score.py"
    output_dir = req.output_dir or ""

    def _run():
        cfg = _cfg.load()
        cmd = [
            sys.executable, str(script),
            "--input",          req.input_dir,
            "--db",             str(DB_PATH),
            "--clip-model",     cfg["clip_model"],
            "--thumb-size",     str(cfg["thumb_size"]),
            "--sort",           cfg["sort"],
            "--dedup-thr",      str(cfg["dedup_threshold"]),
            "--phash-thr",      str(cfg["phash_threshold"]),
            "--neg-weight",     str(cfg["neg_weight"]),
            "--dof-peak-min",   str(cfg["dof_peak_min"]),
            "--dof-ratio",      str(cfg["dof_ratio"]),
            "--blur-penalty-thr", str(cfg["blur_penalty_thr"]),
        ]
        if req.name:
            cmd += ["--session-name", req.name]
        if output_dir:
            cmd += ["--output", output_dir]
        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            unbuf_cmd = [cmd[0], "-u"] + cmd[1:]
            proc = subprocess.Popen(
                unbuf_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                env=env,
            )
            _scan_jobs[job_id]["pid"] = proc.pid
            _persist_jobs()
            _last_persist = [0]
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if line.startswith("PROGRESS:"):
                    try:
                        _, cur, tot = line.split(":")
                        _scan_jobs[job_id]["current"] = int(cur)
                        _scan_jobs[job_id]["total"] = int(tot)
                        # Persist every 50 photos to avoid hammering disk
                        _last_persist[0] += 1
                        if _last_persist[0] % 50 == 0:
                            _persist_jobs()
                    except ValueError:
                        pass
                elif line.startswith("PHASE:"):
                    try:
                        parts = line.split(":")
                        _scan_jobs[job_id]["phase"] = parts[1]
                        if len(parts) > 2 and int(parts[2]) > 0:
                            _scan_jobs[job_id]["total"] = int(parts[2])
                        _persist_jobs()
                    except (ValueError, IndexError):
                        pass
            proc.wait()
            if proc.returncode != 0:
                _scan_jobs[job_id]["status"] = "error"
                _scan_jobs[job_id]["error"] = f"exit code {proc.returncode}"
            else:
                _scan_jobs[job_id]["status"] = "done"
            _persist_jobs()
        except Exception as e:
            _scan_jobs[job_id]["status"] = "error"
            _scan_jobs[job_id]["error"] = str(e)
            _persist_jobs()

    _scan_jobs[job_id] = {"status": "running", "error": None,
                          "current": 0, "total": 0, "phase": "init", "pid": None,
                          "input_dir": req.input_dir}
    _persist_jobs()
    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": job_id, "status": "running",
            "message": "Scan started."}


@app.get("/api/scan-config")
def get_scan_config():
    return _cfg.load()

@app.post("/api/scan-config")
def post_scan_config(body: dict):
    return _cfg.save(body)


@app.get("/api/jobs")
def list_jobs():
    return _scan_jobs


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    if job_id not in _scan_jobs:
        raise HTTPException(404, "Job not found")
    return _scan_jobs[job_id]


@app.get("/api/sessions/{session_id}")
def get_session(session_id: int):
    conn = get_db()
    try:
        row = conn.execute("""
            SELECT s.*, COUNT(CASE WHEN p.selected=1 THEN 1 END) AS selected_count
            FROM sessions s
            LEFT JOIN photos p ON p.session_id = s.id
            WHERE s.id = ?
            GROUP BY s.id
        """, (session_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Session not found")
        return _row_to_dict(row)
    finally:
        conn.close()


@app.patch("/api/sessions/{session_id}")
def update_session(session_id: int, req: SessionUpdate):
    conn = get_db()
    try:
        if req.notes is not None:
            conn.execute("UPDATE sessions SET notes=? WHERE id=?", (req.notes, session_id))
            conn.commit()
        row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Session not found")
        return _row_to_dict(row)
    finally:
        conn.close()


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: int):
    conn = get_db()
    try:
        conn.execute("DELETE FROM photos WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ── Photos ────────────────────────────────────────────────────────────────────

@app.get("/api/sessions/{session_id}/photos")
def list_photos(
    session_id: int,
    sort: str = Query("name", pattern="^(score|name|sharp|group|rating)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    category: str = Query("all"),
    group_id: int = Query(-2),
    special: str = Query("all"),
    min_score: Optional[float] = Query(None),
    search: str = Query(""),
):
    conn = get_db()
    try:
        session_row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not session_row:
            raise HTTPException(404, "Session not found")
        thumb_dir = session_row["thumb_dir"]

        conditions = ["p.session_id = ?"]
        params: list = [session_id]

        if category != "all":
            conditions.append("(p.user_category = ? OR (p.user_category = '' AND p.category = ?))")
            params += [category, category]

        if group_id == -1:
            conditions.append("p.group_id = -1")
        elif group_id >= 0:
            conditions.append("p.group_id = ?")
            params.append(group_id)

        if min_score is not None:
            conditions.append("p.score >= ?")
            params.append(min_score)

        if search:
            conditions.append("p.name LIKE ?")
            params.append(f"%{search}%")

        # special filters
        special_conditions = {
            "best":     "p.best_in_group = 1",
            "unique":   "p.group_id = -1",
            "dof":      "p.dof = 1",
            "blur":     "p.sharp_center < 80",
            "sharp":    "p.sharp_center > 200",
            "smile":    "p.emotion = 'smile'",
            "bad_face": "p.emotion = 'bad'",
            "selected": "p.selected = 1",
        }
        if special in special_conditions:
            conditions.append(special_conditions[special])
        elif special in ("top25", "bot25"):
            # Compute percentile threshold
            scores = [r[0] for r in conn.execute(
                "SELECT score FROM photos WHERE session_id=?", (session_id,)).fetchall()]
            if scores:
                scores_sorted = sorted(scores)
                n = len(scores_sorted)
                idx75 = int(n * 0.75)
                idx25 = int(n * 0.25)
                if special == "top25":
                    conditions.append("p.score >= ?")
                    params.append(scores_sorted[idx75])
                else:
                    conditions.append("p.score <= ?")
                    params.append(scores_sorted[idx25])

        sort_map = {
            "score":  "p.score",
            "name":   "p.name",
            "sharp":  "p.sharp_center",
            "rating": "p.user_rating",
        }
        order_dir = "DESC" if order == "desc" else "ASC"
        where = " AND ".join(conditions)

        if sort == "group":
            # Unique photos (group_id = -1) always at the end;
            # groups ordered ASC/DESC; within each group best score first.
            end_sentinel = "999999" if order_dir == "ASC" else "-999999"
            sql = (
                f"SELECT p.* FROM photos p WHERE {where} "
                f"ORDER BY CASE WHEN p.group_id = -1 THEN {end_sentinel} ELSE p.group_id END {order_dir}, "
                f"p.score DESC"
            )
        else:
            sort_col = sort_map.get(sort, "p.name")
            sql = f"SELECT p.* FROM photos p WHERE {where} ORDER BY {sort_col} {order_dir}"
        rows = conn.execute(sql, params).fetchall()
        return [_photo_with_thumb_url(_row_to_dict(r), thumb_dir) for r in rows]
    finally:
        conn.close()


@app.patch("/api/photos/{photo_id}")
def update_photo(photo_id: int, req: PhotoUpdate):
    conn = get_db()
    try:
        fields, vals = [], []
        if req.selected is not None:
            fields.append("selected=?"); vals.append(1 if req.selected else 0)
        if req.user_category is not None:
            fields.append("user_category=?"); vals.append(req.user_category)
        if req.user_rating is not None:
            fields.append("user_rating=?"); vals.append(req.user_rating)
        if req.notes is not None:
            fields.append("notes=?"); vals.append(req.notes)
        if not fields:
            raise HTTPException(400, "No fields to update")
        vals.append(photo_id)
        conn.execute(f"UPDATE photos SET {', '.join(fields)} WHERE id=?", vals)
        conn.commit()

        row = conn.execute("""
            SELECT p.*, s.thumb_dir FROM photos p
            JOIN sessions s ON p.session_id = s.id
            WHERE p.id=?
        """, (photo_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Photo not found")
        d = _row_to_dict(row)
        thumb_dir = d.pop("thumb_dir")
        return _photo_with_thumb_url(d, thumb_dir)
    finally:
        conn.close()


# ── Stats ─────────────────────────────────────────────────────────────────────

@app.get("/api/sessions/{session_id}/stats")
def get_stats(session_id: int):
    conn = get_db()
    try:
        photos = conn.execute(
            "SELECT score, category, group_id, selected, emotion, dof, sharp_center "
            "FROM photos WHERE session_id=?", (session_id,)).fetchall()
        if not photos:
            return {"total": 0}

        scores = [p["score"] for p in photos]
        min_s, max_s = min(scores), max(scores)
        avg_s = sum(scores) / len(scores)

        # 20-bucket histogram
        rng = max_s - min_s or 1e-9
        buckets = [0] * 20
        for s in scores:
            i = min(19, int((s - min_s) / rng * 20))
            buckets[i] += 1

        cats: dict[str, int] = {}
        for p in photos:
            c = p["category"] or "unknown"
            cats[c] = cats.get(c, 0) + 1

        emotions: dict[str, int] = {}
        for p in photos:
            e = p["emotion"] or "none"
            emotions[e] = emotions.get(e, 0) + 1

        group_counts: dict[int, int] = {}
        for p in photos:
            if p["group_id"] >= 0:
                group_counts[p["group_id"]] = group_counts.get(p["group_id"], 0) + 1

        return {
            "total": len(photos),
            "selected": sum(1 for p in photos if p["selected"]),
            "dof": sum(1 for p in photos if p["dof"]),
            "groups": len(group_counts),
            "group_counts": group_counts,
            "score_min": round(min_s, 4),
            "score_max": round(max_s, 4),
            "score_avg": round(avg_s, 4),
            "score_histogram": buckets,
            "categories": cats,
            "emotions": emotions,
        }
    finally:
        conn.close()


# ── Export ────────────────────────────────────────────────────────────────────

@app.post("/api/sessions/{session_id}/export")
def export_photos(session_id: int, req: ExportRequest):
    conn = get_db()
    try:
        if req.only_selected:
            rows = conn.execute(
                "SELECT id, path, name FROM photos WHERE session_id=? AND selected=1",
                (session_id,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, path, name FROM photos WHERE session_id=?",
                (session_id,)).fetchall()

        dest = Path(req.dest_dir)
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise HTTPException(400, f"Cannot create destination: {e}")

        copied, errors = 0, []
        ids_copied = []
        for row in rows:
            src = Path(row["path"])
            if not src.exists():
                errors.append(f"Not found: {row['name']}")
                continue
            try:
                shutil.copy2(src, dest / src.name)
                xmp = src.with_suffix(".xmp")
                if xmp.exists():
                    shutil.copy2(xmp, dest / xmp.name)
                copied += 1
                ids_copied.append(row["id"])
            except Exception as e:
                errors.append(f"{row['name']}: {e}")

        # Mark exported
        for pid in ids_copied:
            conn.execute(
                "UPDATE photos SET exported=1, export_path=? WHERE id=?",
                (str(dest), pid))
        conn.commit()
        return {"copied": copied, "total": len(rows), "errors": errors, "dest": str(dest)}
    finally:
        conn.close()


# ── Folder picker (native Windows dialog) ────────────────────────────────────

@app.get("/api/pick-folder")
def pick_folder(title: str = Query("Vyberte složku")):
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()
        folder = filedialog.askdirectory(parent=root, title=title)
        root.destroy()
        if folder:
            return {"path": folder.replace("/", "\\")}
        return {"path": ""}
    except Exception as e:
        raise HTTPException(500, f"Picker error: {e}")


# ── File operations ───────────────────────────────────────────────────────────

@app.get("/api/open")
def open_file(path: str = Query(...)):
    p = Path(path)
    if not p.exists():
        raise HTTPException(404, "File not found")
    try:
        os.startfile(str(p))
        return {"ok": True, "path": str(p)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/thumb")
def serve_thumb(path: str = Query(...)):
    p = Path(path)
    if not p.exists():
        raise HTTPException(404, "Thumbnail not found")
    return FileResponse(str(p), media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})


# ── Serve React SPA (production build) ───────────────────────────────────────

_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=str(_dist / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        return FileResponse(str(_dist / "index.html"))
