"""
=============================================================
  PHOTO SCORER v2 – ohodnoceni + HTML dashboard
  Autor: pro Martine
=============================================================

Pouziti:
    python photo_score.py --input "Z:\Foto\RAW\...\serie"

Zaroven spust server pro otevirani souboru:
    python photo_server.py
"""

import argparse, json, sys, time
from pathlib import Path
import io as _io
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def check_deps():
    missing = []
    for pkg, pip in [('torch','torch'),('PIL','Pillow'),('rawpy','rawpy'),
                     ('numpy','numpy'),('tqdm','tqdm'),('clip','openai-clip')]:
        try: __import__(pkg)
        except ImportError: missing.append(pip)
    if missing:
        print('Chybi:', ', '.join(missing))
        print('pip install', ' '.join(missing))
        sys.exit(1)
check_deps()

import torch, clip, rawpy
import numpy as np
from PIL import Image
from tqdm import tqdm

try:
    from scipy.ndimage import convolve as sp_conv
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    from deepface import DeepFace
    HAS_DEEPFACE = True
except ImportError:
    HAS_DEEPFACE = False

SUPPORTED_RAW = {".arw",".nef",".cr2",".cr3",".orf",".rw2",".dng"}

# Embedded DB schema (mirrors backend/schema.sql)
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    input_dir    TEXT NOT NULL,
    thumb_dir    TEXT NOT NULL,
    scanned_at   TEXT NOT NULL,
    total_photos INTEGER DEFAULT 0,
    notes        TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS photos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES sessions(id),
    name            TEXT NOT NULL,
    path            TEXT NOT NULL,
    thumb           TEXT NOT NULL,
    score           REAL DEFAULT 0,
    clip_score      REAL DEFAULT 0,
    sharp_center    REAL DEFAULT 0,
    sharp_edges     REAL DEFAULT 0,
    sharp_total     REAL DEFAULT 0,
    dof             INTEGER DEFAULT 0,
    comp_score      REAL DEFAULT 0,
    category        TEXT DEFAULT '',
    emotion         TEXT DEFAULT '',
    face_score      REAL DEFAULT 0,
    group_id        INTEGER DEFAULT -1,
    best_in_group   INTEGER DEFAULT 0,
    selected        INTEGER DEFAULT 0,
    user_category   TEXT DEFAULT '',
    user_rating     INTEGER DEFAULT 0,
    notes           TEXT DEFAULT '',
    exported        INTEGER DEFAULT 0,
    export_path     TEXT DEFAULT '',
    created_at      TEXT NOT NULL,
    embedding       BLOB DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_photos_session  ON photos(session_id);
CREATE INDEX IF NOT EXISTS idx_photos_score    ON photos(session_id, score DESC);
CREATE INDEX IF NOT EXISTS idx_photos_group    ON photos(session_id, group_id);
CREATE INDEX IF NOT EXISTS idx_photos_selected ON photos(session_id, selected);
"""
SUPPORTED_STD = {".jpg",".jpeg",".png",".tiff",".tif"}
SUPPORTED_ALL = SUPPORTED_RAW | SUPPORTED_STD

# CLIP prompty – kvalita
POS_PROMPTS = [
    "a sharp focused high quality photograph",
    "a professional photograph with perfect exposure and composition",
    "award winning travel and nature photography",
    "a well lit photograph with beautiful colors",
    "a memorable moment captured perfectly",
    "a portrait with sharp focused subject and beautiful soft bokeh background",
]
NEG_PROMPTS = [
    "a completely blurry photo where everything is out of focus with no sharp subject",
    "an overexposed or underexposed photo",
    "a dark grainy low quality snapshot",
    "a poorly composed accidental photo",
]

# CLIP prompty – kategorie
CAT_PROMPTS = {
    "portret_blizky": [
        "a close up portrait face fills the entire frame minimal background",
        "head and shoulders portrait very close to camera face dominates photo",
        "extreme close up of a person face no full body visible",
        "tight facial portrait face occupies most of the image",
    ],
    "portret_vzdaleny": [
        "a person full body visible standing in a landscape",
        "full length portrait of a person outdoors whole body in frame head to toe",
        "person standing in mountains visible from head to toe",
    ],
    "krajina":          [
        "a dramatic mountain landscape with no people",
        "scenic nature landscape, no humans present",
        "wide angle nature photo mountains forest",
    ],
    "detail":           [
        "a macro detail of nature rocks or flowers",
        "close up texture nature photography",
    ],
    "akce":             [
        "people actively climbing hiking or moving in mountains",
        "action outdoor candid moment with people moving",
    ],
    "scena":            [
        "a wide landscape scene with tiny distant people or objects",
        "a person far away small in the frame landscape dominant",
        "distant silhouette in landscape",
    ],
}

# Minimalni CLIP skore rozdilu pro portret_vzdaleny vs scena
# Pokud rozdil mezi portret_vzdaleny a scena < tento prah,
# preferujeme scenu (clovek je moc maly)
PORTRET_V_MARGIN = 0.003

# Minimalni rozdil portret_vzdaleny vs portret_blizky pro povyseni na blizky
# Pokud portret_blizky skoro vyrovnava portret_vzdaleny (< tento prah),
# klasifikujeme jako portret_blizky
PORTRET_B_MARGIN = 0.002

# CLIP prompty – vyraz obliceje (spolehlivejsi nez DeepFace pro outdoor)
FACE_PROMPTS = {
    "smile":   ["a person smiling happily", "a happy smiling face", "joyful expression"],
    "neutral": ["a person with neutral expression", "calm neutral face looking at camera"],
    "bad":     ["a person with eyes closed", "bad expression closed eyes",
                "a person not looking at camera eyes shut"],
}

# ── Pomocne funkce ────────────────────────────────────────────────────────────
def get_device():
    if torch.cuda.is_available():
        gpu  = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"[GPU] {gpu} ({vram:.1f} GB VRAM)")
        return torch.device("cuda")
    return torch.device("cpu")

# ── Binary JPEG fallback (pro RAW soubory kde rawpy visí) ────────────────────
def _extract_jpeg_binary(path: Path) -> "Image.Image | None":
    """Najde největší embedded JPEG v binárním souboru (preview v RAW/ARW).
    Bezpečné – žádný nativní kód, jen skenování bytů."""
    try:
        import io as _io
        data = path.read_bytes()
        best_size = 0
        best_data = None
        pos = 0
        while True:
            idx = data.find(b'\xff\xd8\xff', pos)
            if idx == -1:
                break
            end = data.find(b'\xff\xd9', idx + 4)
            if end != -1:
                size = end + 2 - idx
                if size > best_size:
                    best_size = size
                    best_data = data[idx:end + 2]
            pos = idx + 1
        if best_data is not None:
            return Image.open(_io.BytesIO(best_data)).convert('RGB')
    except Exception:
        pass
    return None


# ── Perzistentní RAW worker (jeden subprocess na celý scan) ───────────────────
_RAW_WORKER_CODE = r"""
import sys, rawpy, numpy as np, io, os

# Unbuffered binary stdout pro předávání dat
out = open(sys.stdout.fileno(), 'wb', buffering=0)
inp = open(sys.stdin.fileno(),  'r',  buffering=1)

while True:
    line = inp.readline()
    if not line:
        break
    parts = line.rstrip('\n').split('\t', 1)
    path_in, tmpf = parts[0], parts[1]
    try:
        with rawpy.imread(path_in) as raw:
            try:
                from rawpy import ThumbFormat
                td = raw.extract_thumb()
                if td.format == ThumbFormat.JPEG:
                    from PIL import Image as _Img
                    img = _Img.open(io.BytesIO(td.data)).convert('RGB')
                    np.save(tmpf, np.array(img))
                    out.write(b'OK\n'); continue
            except Exception:
                pass
            rgb = raw.postprocess(use_camera_wb=True, half_size=True,
                                  no_auto_bright=False, output_bps=8)
            np.save(tmpf, rgb)
            out.write(b'OK\n')
    except Exception as e:
        out.write(b'ERR\n')
"""

class _RawWorker:
    """Jeden perzistentní subprocess pro celý scan. Pokud crashne, restartuje se."""
    def __init__(self):
        self._proc = None
        self._lock = __import__('threading').Lock()
        self._start()

    def _start(self):
        import subprocess as _sp
        self._proc = _sp.Popen(
            [sys.executable, '-u', '-c', _RAW_WORKER_CODE],
            stdin=_sp.PIPE, stdout=_sp.PIPE, stderr=_sp.DEVNULL,
            bufsize=0,
        )

    def _peek_readline(self, timeout=10) -> "bytes | None":
        """Non-blokující readline přes PeekNamedPipe (Windows) nebo thread (ostatní)."""
        import time, os as _os
        if sys.platform == 'win32':
            import ctypes, msvcrt
            try:
                handle = msvcrt.get_osfhandle(self._proc.stdout.fileno())
            except Exception:
                return None
            deadline = time.time() + timeout
            buf = b''
            while time.time() < deadline:
                avail = ctypes.c_ulong(0)
                ok = ctypes.windll.kernel32.PeekNamedPipe(
                    ctypes.c_void_p(handle), None, 0, None,
                    ctypes.byref(avail), None)
                if not ok:
                    break  # roura zavřená (worker padl)
                if avail.value > 0:
                    try:
                        byte = _os.read(self._proc.stdout.fileno(), 1)
                    except Exception:
                        break
                    if not byte:
                        break
                    buf += byte
                    if buf.endswith(b'\n'):
                        return buf
                else:
                    time.sleep(0.05)
            return None
        else:
            import threading as _t
            result = [None]
            def _r():
                try: result[0] = self._proc.stdout.readline()
                except Exception: pass
            t = _t.Thread(target=_r, daemon=True)
            t.start(); t.join(timeout)
            return result[0]

    def load(self, path: Path, timeout: int = 10):
        import tempfile, os as _os
        fd, tmpf = tempfile.mkstemp()
        _os.close(fd)
        try:
            with self._lock:
                try:
                    line = f"{path}\t{tmpf}\n".encode()
                    self._proc.stdin.write(line)
                    self._proc.stdin.flush()
                except Exception:
                    self._start()
                    return _extract_jpeg_binary(path)

                resp = self._peek_readline(timeout)

                if resp is None or self._proc.poll() is not None:
                    print(f"  [WARN] {path.name}: worker crash/timeout, binary fallback", flush=True)
                    try:
                        self._proc.kill()
                        self._proc.wait(timeout=2)  # počkej na uvolnění file handle
                    except Exception: pass
                    self._start()
                    return _extract_jpeg_binary(path)

                if resp.strip() == b'OK':
                    npy = tmpf + '.npy'
                    src = npy if _os.path.exists(npy) else tmpf
                    arr = np.load(src)
                    return Image.fromarray(arr.astype(np.uint8))

                print(f"  [WARN] {path.name}: rawpy ERR, binary fallback", flush=True)
        except Exception as e:
            print(f"  [WARN] {path.name}: {e}", flush=True)
        finally:
            for p in (tmpf, tmpf + '.npy'):
                try: _os.unlink(p)
                except: pass
        return _extract_jpeg_binary(path)

    def close(self):
        try:
            self._proc.stdin.close()
            self._proc.wait(timeout=3)
        except Exception:
            try: self._proc.kill()
            except Exception: pass

_raw_worker: "_RawWorker | None" = None


def load_image(path: Path):
    global _raw_worker
    import time as _t
    try:
        if path.suffix.lower() in SUPPORTED_RAW:
            t0 = _t.time()
            print(f"  [TRACE] load_image: binary_extract start {path.name}", flush=True)
            img = _extract_jpeg_binary(path)
            print(f"  [TRACE] load_image: binary_extract done {_t.time()-t0:.2f}s img={'ok' if img else 'None'}", flush=True)
            if img is not None:
                return img
            print(f"  [TRACE] load_image: falling back to worker {path.name}", flush=True)
            if _raw_worker is None:
                _raw_worker = _RawWorker()
            return _raw_worker.load(path)
        return Image.open(path).convert("RGB")
    except Exception as e:
        print(f"  [WARN] {path.name}: {e}")
        return None

def make_thumbnail(src: Path, dst: Path, size: int, img: "Image.Image | None" = None) -> bool:
    try:
        if img is None:
            if src.suffix.lower() in SUPPORTED_RAW:
                with rawpy.imread(str(src)) as raw:
                    try:
                        td = raw.extract_thumb()
                        if td.format == rawpy.ThumbFormat.JPEG:
                            import io as _b
                            img = Image.open(_b.BytesIO(td.data)).convert("RGB")
                        else: raise ValueError()
                    except Exception:
                        rgb = raw.postprocess(use_camera_wb=True, half_size=True,
                                              no_auto_bright=False, output_bps=8)
                        img = Image.fromarray(rgb)
            else:
                img = Image.open(src).convert("RGB")
        img = img.copy()
        img.thumbnail((size, size), Image.LANCZOS)
        img.save(dst, "JPEG", quality=85, optimize=True)
        return True
    except Exception:
        return False

# ── DOF-aware ostrost ─────────────────────────────────────────────────────────
def analyze_sharpness(img: Image.Image,
                      dof_peak_min: float = 120,
                      dof_ratio: float = 2.5,
                      blur_penalty_thr: float = 40) -> dict:
    """
    Rozlisuje mezi:
      - Ostry objekt + rozmazane pozadi (DOF/bokeh) -> zadna penalizace, bonus
      - Vse rozmazane -> penalizace
      - Vse ostre -> bonus

    DOF detekce pouziva mrizi 4x4 bloku – funguje i pro off-center motivy
    (pravidlo tretin, portret vlevo/vpravo, atd.)
    """
    if not HAS_SCIPY:
        return {"sharp_center": 100.0, "sharp_edges": 100.0,
                "sharp_total": 100.0, "dof": False, "score": 0.0}

    gray = np.array(img.convert("L"), dtype=np.float32)
    h, w = gray.shape
    kern = np.array([[0,1,0],[1,-4,1],[0,1,0]], dtype=np.float32)
    lap  = sp_conv(gray, kern)

    # Stred a okraje – zachovano pro metriky v DB / UI
    cy1, cy2 = int(h*0.3), int(h*0.7)
    cx1, cx2 = int(w*0.3), int(w*0.7)
    center_var = float(np.var(lap[cy1:cy2, cx1:cx2]))

    edge_mask = np.zeros_like(lap, dtype=bool)
    edge_mask[:int(h*0.2), :] = True
    edge_mask[int(h*0.8):, :] = True
    edge_mask[:, :int(w*0.2)] = True
    edge_mask[:, int(w*0.8):] = True
    edge_var  = float(np.var(lap[edge_mask]))
    total_var = float(np.var(lap))

    # DOF detekce: mrize 4x4 bloku – najde nejostrejsi region kdekoliv v obrazu
    GRID = 4
    bh, bw = h // GRID, w // GRID
    block_vars = [
        float(np.var(lap[gy*bh:(gy+1)*bh, gx*bw:(gx+1)*bw]))
        for gy in range(GRID) for gx in range(GRID)
    ]
    block_vars.sort()
    peak_var   = block_vars[-1]                      # nejostrejsi blok
    median_var = block_vars[len(block_vars) // 2]    # median bloku

    dof = (peak_var > dof_peak_min) and (peak_var > median_var * dof_ratio)

    if dof:
        score = min((peak_var - dof_peak_min) / 600.0, 0.2)
    elif peak_var < blur_penalty_thr:
        score = -0.3 + peak_var / 200.0
    else:
        score = min((peak_var - blur_penalty_thr) / 400.0, 0.15)

    return {
        "sharp_center": round(center_var, 1),
        "sharp_edges":  round(edge_var, 1),
        "sharp_total":  round(total_var, 1),
        "dof":          dof,
        "score":        round(float(score), 4),
    }

# ── Kompozice ─────────────────────────────────────────────────────────────────
def composition_score(img: Image.Image) -> float:
    arr  = np.array(img.convert("RGB"), dtype=np.float32) / 255.0
    h, w = arr.shape[:2]
    gray = 0.299*arr[:,:,0] + 0.587*arr[:,:,1] + 0.114*arr[:,:,2]
    gy   = np.abs(np.diff(gray, axis=0, prepend=gray[:1,:]))
    gx   = np.abs(np.diff(gray, axis=1, prepend=gray[:,:1]))
    sal  = gy + gx
    m    = max(h, w) // 10
    ts   = sum(
        float(sal[max(0,ty-m):min(h,ty+m), max(0,tx-m):min(w,tx+m)].mean())
        for ty in [h//3, 2*h//3] for tx in [w//3, 2*w//3]
    )
    gm   = float(sal.mean()) + 1e-6
    score = min(((ts/4)/gm - 1.0) * 0.3, 0.4)
    top   = arr[:h//3]
    if float(top.mean()) > 0.7 and float(1.0 - top.std()) > 0.8:
        score -= float((top > 0.7).mean()) * 0.4
    ew, eh = max(w//15,10), max(h//15,10)
    em = float(np.concatenate([sal[:,:ew].flatten(), sal[:,-ew:].flatten(),
                                sal[:eh,:].flatten(), sal[-eh:,:].flatten()]).mean())
    cm = float(sal[h//4:3*h//4, w//4:3*w//4].mean()) + 1e-6
    if em/cm > 1.2:
        score -= min((em/cm-1.2)*0.5, 0.4)
    return float(np.clip(score, -1.0, 1.0))

# ── CLIP-based vyraz obliceje ─────────────────────────────────────────────────
def analyze_face_clip(img: Image.Image, model, preprocess,
                      tf_face: dict, device) -> dict:
    """
    Pouziva CLIP pro detekci vyrazu – spolehlivejsi nez DeepFace pro outdoor portréty.
    Detekuje: smile / neutral / bad (zavrene oci, spatny vyraz)
    """
    img_t = preprocess(img).unsqueeze(0).to(device)
    with torch.no_grad():
        feat = model.encode_image(img_t)
        feat = feat / feat.norm(dim=-1, keepdim=True)
        scores = {k: (feat @ tf.T).mean().item() for k, tf in tf_face.items()}

    best     = max(scores, key=scores.get)
    smile_s  = scores["smile"]
    bad_s    = scores["bad"]
    gap      = smile_s - bad_s

    if gap > 0.005:
        emotion = "smile"
        fscore  = min(gap * 30, 1.0)
    elif bad_s > smile_s + 0.003:
        emotion = "bad"
        fscore  = -min((bad_s - smile_s) * 30, 0.8)
    else:
        emotion = "neutral"
        fscore  = 0.1

    return {
        "emotion": emotion,
        "face_score": round(float(fscore), 4),
        "smile_sim":  round(float(smile_s), 4),
        "bad_sim":    round(float(bad_s), 4),
    }

# ── Deduplikacni skupiny (CLIP + pHash) ──────────────────────────────────────
try:
    import imagehash
    HAS_IMAGEHASH = True
except ImportError:
    HAS_IMAGEHASH = False

def phash_similarity(h1, h2) -> float:
    """Vraci podobnost 0.0-1.0 (1.0 = identicke pixely)."""
    diff = h1 - h2  # Hammingova vzdalenost (0-64)
    return 1.0 - diff / 64.0

def find_dedup_groups(embeddings: list, phashes: list, threshold: float,
                      phash_threshold: float = 0.83) -> list:
    """
    Skupiny s tranzitivnim spojenım (Union-Find):
      - A~B a B~C => A, B, C ve stejne skupine, i kdyz A primo nesplni prah s C
      - Podminka 1: CLIP cosine similarity >= threshold
      - Podminka 2: pHash podobnost >= phash_threshold

    phashes: predpocitane haše (imagehash objekt nebo None) – pocitaji se v loopu,
             ne zde, aby se nemusely drzet vsechny obrazky v pameti.
    Bez imagehash: pouzije se prisnejsi CLIP prah (threshold + 0.04).
    """
    n = len(embeddings)
    if n == 0:
        return []

    emb_arr = np.array(embeddings, dtype=np.float32)
    clip_threshold = threshold if HAS_IMAGEHASH else min(threshold + 0.04, 0.99)

    # Vsechny pairwise CLIP similarity najednou (matice n×n) – rychle pro velke serie
    sim_matrix = emb_arr @ emb_arr.T

    # Union-Find – umoznuje tranzitivni skupiny
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i in range(n):
        for j in range(i + 1, n):
            if sim_matrix[i, j] < clip_threshold:
                continue
            if HAS_IMAGEHASH and phashes[i] is not None and phashes[j] is not None:
                diff   = phashes[i] - phashes[j]
                ph_sim = 1.0 - diff / 256.0
                if ph_sim < phash_threshold:
                    continue
            union(i, j)

    # Preved Union-Find koreny na ocislovane group_id, osamele = -1
    from collections import defaultdict
    root_members = defaultdict(list)
    for i in range(n):
        root_members[find(i)].append(i)

    groups = [-1] * n
    gid = 0
    for members in root_members.values():
        if len(members) > 1:
            for idx in members:
                groups[idx] = gid
            gid += 1

    return groups

# ── Hlavni scorer ─────────────────────────────────────────────────────────────
def save_to_db(results: list, input_dir: Path, output_dir: Path,
               db_path: Path, session_name: str = "") -> int:
    import sqlite3 as _sqlite3
    from datetime import datetime as _dt

    name = session_name or input_dir.name
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)
    for _migration in ["ALTER TABLE photos ADD COLUMN embedding BLOB DEFAULT NULL"]:
        try:
            conn.execute(_migration); conn.commit()
        except _sqlite3.OperationalError:
            pass
    conn.execute("""
        INSERT INTO sessions (name, input_dir, thumb_dir, scanned_at, total_photos)
        VALUES (?, ?, ?, ?, ?)
    """, (name, str(input_dir), str(output_dir),
          _dt.now().isoformat(), len(results)))
    session_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for r in results:
        emb_blob = r["embedding"].tobytes() if r.get("embedding") is not None else None
        conn.execute("""
            INSERT INTO photos (
                session_id, name, path, thumb,
                score, clip_score, sharp_center, sharp_edges, sharp_total,
                dof, comp_score, category, emotion, face_score,
                group_id, best_in_group, created_at, embedding
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            session_id, r["name"], r["path"], r["thumb"],
            r["score"], r["clip"], r["sharp_c"], r["sharp_e"], r["sharp_t"],
            1 if r["dof"] else 0, r["comp"], r["category"],
            r["emotion"], r["face_score"],
            r["group"], 1 if r["best_in_group"] else 0,
            _dt.now().isoformat(), emb_blob
        ))
    conn.commit()
    conn.close()
    return session_id


def score_photos(input_dir: Path, output_dir: Path, sort_by: str,
                 thumb_size: int, dedup_threshold: float,
                 db_path: Path = None, session_name: str = "",
                 clip_model: str = "ViT-L/14", neg_weight: float = 0.7,
                 phash_threshold: float = 0.83, dof_peak_min: float = 120,
                 dof_ratio: float = 2.5, blur_penalty_thr: float = 40,
                 skip_files: list = None, start_from: int = 0):
    print("\n" + "="*60)
    print("  PHOTO SCORER v2")
    print("="*60)

    skip_set = {s.strip().lower() for s in (skip_files or []) if s.strip()}

    photos = sorted([
        p for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_ALL
        and p.name.lower() not in skip_set
    ])
    if start_from > 0:
        print(f"[INFO] Přeskakuji prvních {start_from} souborů (start_from={start_from})", flush=True)
        photos = photos[start_from:]
    if not photos:
        print(f"[ERR] Zadne fotky v {input_dir}")
        sys.exit(1)

    print(f"[DIR]   {input_dir}")
    print(f"[COUNT] {len(photos)} fotek")
    if not HAS_SCIPY:
        print("[WARN]  scipy chybi – pip install scipy (pro ostrost)")

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "_thumbs").mkdir(exist_ok=True)

    # Nacti CLIP
    print(f"PHASE:loading_model:{len(photos)}", flush=True)
    print("\n[WAIT] Nacitam CLIP model...")
    device = get_device()
    print(f"[CFG]   model={clip_model}  neg_weight={neg_weight}  dedup={dedup_threshold}  phash={phash_threshold}  dof_peak={dof_peak_min}  dof_ratio={dof_ratio}  blur_thr={blur_penalty_thr}")
    model, preprocess = clip.load(clip_model, device=device)
    model.eval()

    with torch.no_grad():
        tf_pos = model.encode_text(clip.tokenize(POS_PROMPTS).to(device))
        tf_pos = tf_pos / tf_pos.norm(dim=-1, keepdim=True)
        tf_neg = model.encode_text(clip.tokenize(NEG_PROMPTS).to(device))
        tf_neg = tf_neg / tf_neg.norm(dim=-1, keepdim=True)
        tf_cats = {}
        for k, prompts in CAT_PROMPTS.items():
            t = model.encode_text(clip.tokenize(prompts).to(device))
            tf_cats[k] = t / t.norm(dim=-1, keepdim=True)
        tf_face = {}
        for k, prompts in FACE_PROMPTS.items():
            t = model.encode_text(clip.tokenize(prompts).to(device))
            tf_face[k] = t / t.norm(dim=-1, keepdim=True)

    print(f"\n[SCAN] Hodnotim {len(photos)} fotek...\n")
    print(f"PHASE:scanning:{len(photos)}", flush=True)
    results    = []
    embeddings = []
    phash_list = []
    start      = time.time()

    for _i, photo_path in enumerate(tqdm(photos, unit="foto")):
        print(f"PROGRESS:{_i+1}:{len(photos)}", flush=True)
        print(f"FILE:{photo_path.name}", flush=True)
        _step_t = time.time()
        img = load_image(photo_path)
        print(f"  [TRACE] load_image done {time.time()-_step_t:.2f}s", flush=True)
        if img is None:
            continue

        # CLIP embedding + quality score
        _step_t = time.time()
        img_t = preprocess(img).unsqueeze(0).to(device)
        with torch.no_grad():
            feat = model.encode_image(img_t)
            feat = feat / feat.norm(dim=-1, keepdim=True)
            pos  = (feat @ tf_pos.T).mean().item()
            neg  = (feat @ tf_neg.T).mean().item()
            cat_s = {k: (feat @ tf.T).mean().item() for k, tf in tf_cats.items()}
        clip_s = float(pos - neg * neg_weight)
        emb    = feat.cpu().numpy().squeeze()
        embeddings.append(emb)
        print(f"  [TRACE] clip done {time.time()-_step_t:.2f}s", flush=True)

        # pHash ihned – obraz se pak uvolni
        if HAS_IMAGEHASH:
            try:
                phash_list.append(imagehash.phash(img, hash_size=16))
            except Exception:
                phash_list.append(None)
        else:
            phash_list.append(None)

        # Kategorie – s korekcí pro portret_vzdaleny vs scena
        category = max(cat_s, key=cat_s.get)

        # portret_vzdaleny vs scena: pokud rozdil maly -> degraduj na scena
        if category == "portret_vzdaleny":
            if cat_s["portret_vzdaleny"] - cat_s.get("scena", 0) < PORTRET_V_MARGIN:
                category = "scena"

        # portret_vzdaleny vs portret_blizky: pokud blizky skoro vyrovnava -> povys na blizky
        if category == "portret_vzdaleny":
            if cat_s["portret_vzdaleny"] - cat_s.get("portret_blizky", 0) < PORTRET_B_MARGIN:
                category = "portret_blizky"

        is_portrait = category in ("portret_blizky", "portret_vzdaleny")

        # Ostrost (DOF-aware)
        _step_t = time.time()
        sharp = analyze_sharpness(img, dof_peak_min, dof_ratio, blur_penalty_thr)
        print(f"  [TRACE] sharp done {time.time()-_step_t:.2f}s", flush=True)

        # Kompozice
        _step_t = time.time()
        comp = round(composition_score(img), 3)
        print(f"  [TRACE] comp done {time.time()-_step_t:.2f}s", flush=True)

        # Vyraz obliceje (CLIP-based, jen pro portréty)
        face = {"emotion": "", "face_score": 0.0, "smile_sim": 0.0, "bad_sim": 0.0}
        if is_portrait:
            _step_t = time.time()
            face = analyze_face_clip(img, model, preprocess, tf_face, device)
            print(f"  [TRACE] face done {time.time()-_step_t:.2f}s", flush=True)

        # Celkove skore
        total = clip_s + sharp["score"] + comp * 0.2
        if is_portrait and face["emotion"]:
            total += face["face_score"] * 0.3

        # Thumbnail
        _step_t = time.time()
        tname = f"{photo_path.stem}.jpg"
        make_thumbnail(photo_path, output_dir / "_thumbs" / tname, thumb_size, img=img)
        print(f"  [TRACE] thumb done {time.time()-_step_t:.2f}s", flush=True)

        results.append({
            "name":      photo_path.name,
            "path":      str(photo_path).replace("\\", "/"),
            "thumb":     f"_thumbs/{tname}",
            "score":     round(total, 4),
            "clip":      round(clip_s, 4),
            "sharp_c":   sharp["sharp_center"],
            "sharp_e":   sharp["sharp_edges"],
            "sharp_t":   sharp["sharp_total"],
            "dof":       sharp["dof"],
            "comp":      comp,
            "category":  category,
            "emotion":   face["emotion"],
            "face_score":face["face_score"],
            "group":     -1,
            "best_in_group": False,
            "embedding": emb,  # numpy float32 – ulozeno do DB jako BLOB
        })

        del img
        if device.type == "cuda":
            torch.cuda.empty_cache()

    elapsed = time.time() - start
    print(f"\n[TIME] {elapsed:.1f}s  ({elapsed/max(len(results),1):.2f}s/foto)")

    if _raw_worker:
        _raw_worker.close()

    # Deduplikacni skupiny
    print(f"PHASE:dedup:0", flush=True)
    print(f"[DEDUP] Hledam skupiny (CLIP>={dedup_threshold:.2f} + pHash>=0.85)...")
    if not HAS_IMAGEHASH:
        print("[WARN]  imagehash chybi – pouzivam jen CLIP (mene presne)")
        print("        pip install imagehash")
    groups = find_dedup_groups(embeddings, phash_list, dedup_threshold, phash_threshold)
    for i, r in enumerate(results):
        r["group"] = int(groups[i])

    # Nejlepsi v kazde skupine
    from collections import defaultdict
    group_map = defaultdict(list)
    for i, r in enumerate(results):
        if r["group"] >= 0:
            group_map[r["group"]].append((i, r["score"]))
    for gid, members in group_map.items():
        best_idx = max(members, key=lambda x: x[1])[0]
        results[best_idx]["best_in_group"] = True

    print(f"       Skupin celkem: {len(group_map)}")
    print(f"       Fotek ve skupinach: {sum(len(v) for v in group_map.values())}")
    # Vypis skupin > 2 fotky pro kontrolu
    large_groups = {gid: members for gid, members in group_map.items() if len(members) > 2}
    if large_groups:
        print(f"       Velke skupiny (>2 fotky):")
        for gid, members in sorted(large_groups.items(), key=lambda x: -len(x[1]))[:5]:
            names = [results[i]["name"] for i, _ in members[:4]]
            more  = f" +{len(members)-4} dalsich" if len(members) > 4 else ""
            print(f"         gr.{gid}: {', '.join(names)}{more}")

    # Razeni
    if sort_by == "score":
        results_display = sorted(results, key=lambda r: r["score"], reverse=True)
    else:
        results_display = sorted(results, key=lambda r: r["name"])

    # Generuj dashboard
    html_path = output_dir / "dashboard.html"
    generate_dashboard(results_display, results, html_path, input_dir)
    print(f"[HTML] {html_path}")
    print(f"[OK]   {len(results)} fotek ohodnoceno\n")

    if db_path:
        print(f"PHASE:saving:0", flush=True)
        sid = save_to_db(results, input_dir, output_dir, db_path, session_name)
        print(f"[DB]   Session #{sid} ulozena do {db_path}")

    print(f"  Spust server pro otevirani souboru:")
    print(f"  python photo_server.py\n")


# ── HTML dashboard ────────────────────────────────────────────────────────────
def generate_dashboard(results_display, results_all, html_path: Path, input_dir: Path):

    scores    = [r["score"] for r in results_all]
    min_s, max_s = min(scores), max(scores)
    avg_s     = sum(scores)/len(scores)
    sharp_avg = sum(r["sharp_c"] for r in results_all)/len(results_all)
    cats      = {}
    for r in results_all:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    dof_cnt   = sum(1 for r in results_all if r["dof"])
    grp_cnt   = len(set(r["group"] for r in results_all if r["group"] >= 0))

    # JSON pro JS (embedding neni serializovatelne, vynechame)
    _skip = {"embedding"}
    jdata = json.dumps([{k: v for k, v in r.items() if k not in _skip} for r in results_all])

    # Karty
    cards = ""
    for r in results_display:
        s_pct = int(max(0, min(100, (r["score"]-min_s)/max(max_s-min_s,0.001)*100)))

        # Skupinovy badge
        grp_badge = ""
        if r["group"] >= 0:
            if r["best_in_group"]:
                grp_badge = f'<span class="badge best">★ nejlepsi gr.{r["group"]}</span>'
            else:
                grp_badge = f'<span class="badge grp">gr.{r["group"]}</span>'

        # DOF badge
        dof_badge = '<span class="badge dof">BOKEh</span>' if r["dof"] else ""

        # Ostrost badge
        if r["sharp_c"] < 50:
            sharp_badge = f'<span class="badge bad">blur:{r["sharp_c"]:.0f}</span>'
        elif r["sharp_c"] > 300:
            sharp_badge = f'<span class="badge good">sharp:{r["sharp_c"]:.0f}</span>'
        else:
            sharp_badge = ""

        # Vyraz
        face_badge = ""
        if r["emotion"] == "smile":
            face_badge = '<span class="badge smile">smile</span>'
        elif r["emotion"] == "bad":
            face_badge = '<span class="badge bad">bad-face</span>'

        # Kategorie
        cat_short = {
            "portret_blizky":"portret-B","portret_vzdaleny":"portret-V",
            "krajina":"krajina","detail":"detail","akce":"akce",
            "scena":"scena"
        }.get(r["category"], r["category"])
        cat_badge = f'<span class="badge cat">{cat_short}</span>'

        # Barva skupiny – jemne podbarveni pozadi karty
        # Pouzivame HSL s ruznym hue pro kazde group_id
        # Unikatni fotky (group -1) nemaji podbarveni
        if r["group"] >= 0:
            hue        = (r["group"] * 47) % 360  # 47 = prvocislo, dobra distribuce barev
            grp_style  = f"--grp-color:hsl({hue},60%,15%);--grp-border:hsl({hue},60%,30%)"
            grp_class  = "in-group"
        else:
            grp_style  = ""
            grp_class  = ""

        cards += f'''
        <div class="card {grp_class}"
             style="{grp_style}"
             data-score="{r['score']}"
             data-name="{r['name']}"
             data-path="{r['path']}"
             data-cat="{r['category']}"
             data-group="{r['group']}"
             data-best="{str(r['best_in_group']).lower()}"
             data-dof="{str(r['dof']).lower()}"
             data-sharp="{r['sharp_c']}"
             data-emotion="{r['emotion']}">
          <div class="thumb-wrap" onclick="openFile('{r['path']}')" title="Otevrit: {r['name']}">
            <img src="{r['thumb']}" alt="{r['name']}" loading="lazy">
            <div class="thumb-overlay">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
                   stroke="currentColor" stroke-width="2.5">
                <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
              </svg>
            </div>
          </div>
          <div class="card-info">
            <div class="score-row">
              <span class="score-val">{r['score']:.4f}</span>
              <div class="score-bar"><div class="score-fill" style="width:{s_pct}%"></div></div>
            </div>
            <div class="fname">{r['name']}</div>
            <div class="metrics">clip:{r['clip']:.3f} sh:{r['sharp_c']:.0f}/{r['sharp_e']:.0f} comp:{r['comp']:+.2f}</div>
            <div class="badges">{cat_badge}{grp_badge}{dof_badge}{sharp_badge}{face_badge}</div>
            <label class="sel-row" onclick="event.stopPropagation()">
              <input type="checkbox" class="sel-cb" data-path="{r['path']}" data-name="{r['name']}"
                     onchange="onCheck(this)">
              <span class="sel-label">Vybrat do dalsi faze</span>
            </label>
          </div>
        </div>'''

    # Statistiky kategorii
    cat_stats = " &nbsp;|&nbsp; ".join(
        f"{k.replace('portret_','P-').replace('krajina','KR').replace('detail','DT').replace('akce','AK')}: {v}"
        for k, v in sorted(cats.items(), key=lambda x: -x[1])
    )

    html = f'''<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<title>Photo Scorer – {input_dir.name}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Syne:wght@700;800&display=swap');
:root{{
  --bg:#0c0c0e; --surf:#131316; --border:#1e1e24;
  --accent:#e8a020; --accent2:#3d9eff; --text:#b8b8c8; --muted:#484858;
  --good:#27ae60; --bad:#c0392b; --info:#2980b9;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'JetBrains Mono',monospace;background:var(--bg);color:var(--text);min-height:100vh}}

/* Header */
.header{{background:var(--surf);border-bottom:1px solid var(--border);
         padding:1rem 1.5rem .8rem;position:sticky;top:0;z-index:100}}
.hrow1{{display:flex;align-items:baseline;gap:.8rem;margin-bottom:.6rem}}
.title{{font-family:'Syne',sans-serif;font-size:1.3rem;font-weight:800;color:var(--accent)}}
.dir{{font-size:.72rem;color:var(--muted)}}
.stats{{font-size:.68rem;color:var(--muted);margin-bottom:.7rem;line-height:1.8}}
.stats strong{{color:var(--text)}}

/* Controls */
.ctrl-row{{display:flex;gap:.4rem;flex-wrap:wrap;align-items:center;margin-bottom:.4rem}}
.ctrl-label{{font-size:.65rem;color:var(--muted);min-width:3.5rem}}
.btn{{font-family:'JetBrains Mono',monospace;font-size:.65rem;padding:.25rem .55rem;
      border-radius:3px;border:1px solid var(--border);background:var(--surf);
      color:var(--muted);cursor:pointer;transition:all .12s;white-space:nowrap}}
.btn:hover,.btn.active{{border-color:var(--accent);color:var(--accent);
                         background:rgba(232,160,32,.07)}}
.count{{font-size:.65rem;color:var(--muted);margin-left:auto}}
.count strong{{color:var(--accent)}}

/* Range slider */
.range-wrap{{display:flex;align-items:center;gap:.4rem;font-size:.65rem;color:var(--muted)}}
input[type=range]{{-webkit-appearance:none;width:120px;height:3px;
                   background:var(--border);border-radius:2px;outline:none}}
input[type=range]::-webkit-slider-thumb{{-webkit-appearance:none;width:12px;height:12px;
  border-radius:50%;background:var(--accent);cursor:pointer}}

/* Histogram */
.hist-wrap{{padding:.3rem 1.5rem 0}}
.hist-label{{font-size:.6rem;color:var(--muted);margin-bottom:.2rem}}
canvas{{width:100%;height:32px}}

/* Grid */
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(var(--card-size,200px),1fr));
       gap:.7rem;padding:1rem 1.2rem}}

/* Card */
.card{{background:var(--surf);border:1px solid var(--border);border-radius:7px;
       overflow:hidden;transition:transform .12s,border-color .12s,box-shadow .12s}}
.card:hover{{transform:translateY(-2px);border-color:var(--accent);
             box-shadow:0 6px 20px rgba(0,0,0,.5)}}
.card.hidden{{display:none}}
.card.highlight{{border-color:var(--accent2)!important;
                 box-shadow:0 0 0 1px var(--accent2)}}

/* Thumb */
.thumb-wrap{{position:relative;aspect-ratio:3/2;overflow:hidden;
             background:#0a0a0c;cursor:pointer}}
.thumb-wrap img{{width:100%;height:100%;object-fit:cover;display:block;transition:transform .25s}}
.card:hover .thumb-wrap img{{transform:scale(1.03)}}
.thumb-overlay{{position:absolute;inset:0;background:rgba(0,0,0,.45);
                display:flex;align-items:center;justify-content:center;
                opacity:0;transition:opacity .15s;color:#fff}}
.thumb-wrap:hover .thumb-overlay{{opacity:1}}

/* Info */
.card-info{{padding:.5rem .6rem .6rem}}
.score-row{{display:flex;align-items:center;gap:.4rem;margin-bottom:.25rem}}
.score-val{{font-size:.82rem;font-weight:700;color:var(--accent);min-width:3.2rem}}
.score-bar{{flex:1;height:3px;background:var(--border);border-radius:2px;overflow:hidden}}
.score-fill{{height:100%;background:linear-gradient(90deg,var(--accent2),var(--accent));border-radius:2px}}
.fname{{font-size:.63rem;color:var(--muted);white-space:nowrap;
        overflow:hidden;text-overflow:ellipsis;margin-bottom:.25rem}}
.metrics{{font-size:.58rem;color:#2e2e3e;margin-bottom:.3rem}}
.badges{{display:flex;flex-wrap:wrap;gap:.2rem}}
.badge{{font-size:.58rem;padding:.08rem .28rem;border-radius:2px}}
.badge.cat{{background:rgba(61,158,255,.1);color:#3d9eff}}
.badge.best{{background:rgba(232,160,32,.15);color:var(--accent);font-weight:700}}
.badge.grp{{background:rgba(255,255,255,.05);color:var(--muted)}}
.badge.dof{{background:rgba(155,89,182,.15);color:#9b59b6}}
.badge.good{{background:rgba(39,174,96,.12);color:var(--good)}}
.badge.bad{{background:rgba(192,57,43,.12);color:var(--bad)}}
.badge.smile{{background:rgba(39,174,96,.15);color:#2ecc71;font-weight:600}}

.grp-nav-btn{{transition:all .12s}}
.grp-nav-btn:hover{{opacity:.85}}
.card.in-group{{
  background: var(--grp-color, var(--surf));
  border-color: var(--grp-border, var(--border));
}}
.card.in-group:hover{{
  border-color: var(--accent);
}}
.card.in-group.selected{{
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 2px rgba(232,160,32,.3) !important;
}}
.sel-row{{display:flex;align-items:center;gap:.4rem;margin-top:.4rem;
          padding-top:.4rem;border-top:1px solid var(--border);cursor:pointer}}
.sel-cb{{width:14px;height:14px;accent-color:var(--accent);cursor:pointer;flex-shrink:0}}
.sel-label{{font-size:.62rem;color:var(--muted);user-select:none}}
.card.selected{{border-color:var(--accent)!important;
                box-shadow:0 0 0 2px rgba(232,160,32,.3)!important}}
.card.selected .sel-label{{color:var(--accent)}}

/* Selection bar */
#sel-bar{{position:fixed;bottom:0;left:0;right:0;
          background:var(--surf);border-top:1px solid var(--accent);
          padding:.7rem 1.5rem;display:flex;align-items:center;gap:1rem;
          z-index:200;transform:translateY(100%);transition:transform .2s}}
#sel-bar.visible{{transform:translateY(0)}}
#sel-bar .sel-info{{font-size:.8rem;color:var(--accent);font-weight:700}}
#sel-bar .sel-files{{font-size:.65rem;color:var(--muted);flex:1}}
.sel-btn{{font-family:'JetBrains Mono',monospace;font-size:.7rem;
          padding:.35rem .8rem;border-radius:4px;cursor:pointer;border:none;
          font-weight:600}}
.sel-btn.primary{{background:var(--accent);color:#000}}
.sel-btn.primary:hover{{background:#ffb820}}
.sel-btn.secondary{{background:var(--border);color:var(--text)}}
.sel-btn.secondary:hover{{background:#2a2a32}}
#notif{{position:fixed;bottom:1.5rem;right:1.5rem;background:var(--surf);
        border:1px solid var(--accent);border-radius:6px;padding:.6rem 1rem;
        font-size:.72rem;color:var(--accent);opacity:0;transition:opacity .2s;
        pointer-events:none;z-index:999}}
#notif.show{{opacity:1}}
</style>
</head>
<body>

<div class="header">
  <div class="hrow1">
    <span class="title">PHOTO SCORER</span>
    <span class="dir">{input_dir}</span>
  </div>
  <div class="stats">
    Fotek: <strong>{len(results_all)}</strong> &nbsp;|&nbsp;
    Score avg/min/max: <strong>{avg_s:.4f}</strong> / <strong>{min_s:.4f}</strong> / <strong>{max_s:.4f}</strong> &nbsp;|&nbsp;
    Avg ostrost: <strong>{sharp_avg:.0f}</strong> &nbsp;|&nbsp;
    DOF/bokeh: <strong>{dof_cnt}</strong> &nbsp;|&nbsp;
    Skupin: <strong>{grp_cnt}</strong>
    <br>{cat_stats}
  </div>

  <div class="ctrl-row">
    <span class="ctrl-label">Razeni:</span>
    <button class="btn active" id="btn-name" onclick="sortCards('name')">Nazev</button>
    <button class="btn" id="btn-score" onclick="sortCards('score')">Score</button>
    <button class="btn" id="btn-sharp" onclick="sortCards('sharp')">Ostrost</button>
    <button class="btn" id="btn-group" onclick="sortCards('group')">Skupina</button>
  </div>

  <div class="ctrl-row">
    <span class="ctrl-label">Kategorie:</span>
    <button class="btn active" onclick="filterCat('all')">Vse</button>
    <button class="btn" onclick="filterCat('portret_blizky')">Portret-B</button>
    <button class="btn" onclick="filterCat('portret_vzdaleny')">Portret-V</button>
    <button class="btn" onclick="filterCat('krajina')">Krajina</button>
    <button class="btn" onclick="filterCat('detail')">Detail</button>
    <button class="btn" onclick="filterCat('akce')">Akce</button>
    <button class="btn" onclick="filterCat('scena')">Scena</button>
  </div>

  <div class="ctrl-row">
    <span class="ctrl-label">Filtr:</span>
    <button class="btn active" onclick="filterSpecial('all')">Vse</button>
    <button class="btn" onclick="filterSpecial('best')">Nejlepsi ve skupine</button>
    <button class="btn" onclick="filterSpecial('unique')">Unikatni (bez skupiny)</button>
    <button class="btn" onclick="filterSpecial('dof')">DOF/bokeh</button>
    <button class="btn" onclick="filterSpecial('blur')">Rozmazane</button>
    <button class="btn" onclick="filterSpecial('sharp')">Ostre</button>
    <button class="btn" onclick="filterSpecial('smile')">Usmev</button>
    <button class="btn" onclick="filterSpecial('bad_face')">Spatny vyraz</button>
    <button class="btn" onclick="filterSpecial('top25')">Top 25%</button>
    <button class="btn" onclick="filterSpecial('bot25')">Spodnich 25%</button>
  </div>

  <div class="ctrl-row" id="group-row">
    <span class="ctrl-label">Skupina:</span>
    <button class="btn active" id="grp-btn-all" onclick="filterGroup(-2)">Vse</button>
    <button class="btn" id="grp-btn-none" onclick="filterGroup(-1)">Unikatni</button>
    <div id="grp-btns" style="display:flex;flex-wrap:wrap;gap:.4rem"></div>
    <span style="font-size:.6rem;color:var(--muted);margin-left:.3rem" id="grp-nav-hint"></span>
  </div>

  <div class="ctrl-row">
    <span class="ctrl-label">Min score:</span>
    <div class="range-wrap">
      <input type="range" id="score-range" min="0" max="100" value="0"
             oninput="filterScore(this.value)">
      <span id="score-range-val">0%</span>
    </div>
    <span class="ctrl-label" style="margin-left:1rem">Velikost:</span>
    <div class="range-wrap">
      <input type="range" id="size-range" min="150" max="600" value="200" step="10"
             oninput="resizeCards(this.value)">
      <span id="size-range-val">200px</span>
    </div>
    <span class="count">Zobrazeno: <strong id="vis-count">{len(results_all)}</strong></span>
  </div>
</div>

<div class="hist-wrap">
  <div class="hist-label">Distribuce score</div>
  <canvas id="hist"></canvas>
</div>

<div class="grid" id="grid">{cards}</div>
<div id="notif"></div>

<!-- Selection bar -->
<div id="sel-bar">
  <span class="sel-info" id="sel-count-label">0 vybrano</span>
  <span class="sel-files" id="sel-files-preview"></span>
  <button class="sel-btn secondary" onclick="selectVisible()">Vybrat viditelne</button>
  <button class="sel-btn secondary" onclick="clearSelection()">Zrusit vyber</button>
  <button class="sel-btn primary" onclick="copySelected()">Kopirovat vybrane →</button>
</div>

<script>
const DATA  = {jdata};
const minS  = {min_s};
const maxS  = {max_s};
const scores = DATA.map(d => d.score);

// ── Histogram ────────────────────────────────────────────────────────────────
(function(){{
  const cv = document.getElementById('hist');
  const W  = cv.parentElement.clientWidth || 800;
  const H  = 32;
  cv.width = W; cv.height = H;
  const ctx = cv.getContext('2d');
  const B = 80, cnts = new Array(B).fill(0);
  scores.forEach(s => {{
    const i = Math.min(B-1, Math.floor((s-minS)/(maxS-minS+1e-9)*B));
    cnts[i]++;
  }});
  const mc = Math.max(...cnts);
  cnts.forEach((c,i) => {{
    const x = i/B*W, bw = W/B-0.5, bh = c/mc*H;
    ctx.fillStyle = `hsl(${{190+i/B*50}},65%,45%)`;
    ctx.fillRect(x, H-bh, bw, bh);
  }});
}})();

// ── Skupiny – dynamicke tlacitka ─────────────────────────────────────────────
(function() {{
  // Zjisti vsechny unikatni skupiny a jejich velikosti
  const grpMap = {{}};
  DATA.forEach(d => {{
    if (d.group >= 0) {{
      if (!grpMap[d.group]) grpMap[d.group] = 0;
      grpMap[d.group]++;
    }}
  }});
  const grpIds = Object.keys(grpMap).map(Number).sort((a,b) => a-b);
  const container = document.getElementById('grp-btns');
  const hint = document.getElementById('grp-nav-hint');

  if (grpIds.length === 0) {{
    hint.textContent = '(zadne skupiny)';
    return;
  }}
  hint.textContent = grpIds.length + ' skupin, klaves ← → pro navigaci';

  grpIds.forEach(gid => {{
    const hue = (gid * 47) % 360;
    const cnt = grpMap[gid];
    const btn = document.createElement('button');
    btn.className = 'btn grp-nav-btn';
    btn.id = `grp-btn-${{gid}}`;
    btn.textContent = `gr.${{gid}} (${{cnt}})`;
    btn.style.borderColor = `hsl(${{hue}},50%,35%)`;
    btn.style.color = `hsl(${{hue}},70%,65%)`;
    btn.onclick = () => filterGroup(gid);
    container.appendChild(btn);
  }});

  // Klavesove zkratky ← → pro navigaci mezi skupinami
  let currentGrpIdx = -1;  // -1 = vse
  document.addEventListener('keydown', e => {{
    if (e.target.tagName === 'INPUT') return;
    if (e.key === 'ArrowRight') {{
      currentGrpIdx = Math.min(currentGrpIdx + 1, grpIds.length - 1);
      filterGroup(grpIds[currentGrpIdx]);
    }} else if (e.key === 'ArrowLeft') {{
      currentGrpIdx = Math.max(currentGrpIdx - 1, -1);
      if (currentGrpIdx === -1) filterGroup(-2);
      else filterGroup(grpIds[currentGrpIdx]);
    }}
  }});
}})();

// ── Filtr skupiny ─────────────────────────────────────────────────────────────
let activeGroup = -2;  // -2 = vse, -1 = unikatni, 0+ = konkretni skupina

function filterGroup(gid) {{
  activeGroup = gid;
  // Aktualizuj aktivni tlacitko
  document.querySelectorAll('.grp-nav-btn, #grp-btn-all, #grp-btn-none')
    .forEach(b => b.classList.remove('active'));
  if (gid === -2)      document.getElementById('grp-btn-all').classList.add('active');
  else if (gid === -1) document.getElementById('grp-btn-none').classList.add('active');
  else {{
    const btn = document.getElementById(`grp-btn-${{gid}}`);
    if (btn) btn.classList.add('active');
  }}
  applyFilters();
}}

// ── Stav filtru ───────────────────────────────────────────────────────────────
let activeCat     = 'all';
let activeSpecial = 'all';
let minScorePct   = 0;

// ── Velikost karet ────────────────────────────────────────────────────────────
function resizeCards(val) {{
  document.getElementById('size-range-val').textContent = val + 'px';
  document.getElementById('grid').style.setProperty('--card-size', val + 'px');
}}

function applyFilters() {{
  const cards = Array.from(document.querySelectorAll('.card'));
  const q25 = minS + (maxS-minS)*0.25;
  const q75 = minS + (maxS-minS)*0.75;
  const scoreThresh = minS + (maxS-minS)*(minScorePct/100);
  let vis = 0;

  cards.forEach(c => {{
    const cat    = c.dataset.cat;
    const group  = parseInt(c.dataset.group);
    const best   = c.dataset.best === 'true';
    const dof    = c.dataset.dof === 'true';
    const sharp  = parseFloat(c.dataset.sharp);
    const emo    = c.dataset.emotion;
    const score  = parseFloat(c.dataset.score);

    let show = true;
    if (activeCat !== 'all' && cat !== activeCat) show = false;
    if (score < scoreThresh) show = false;
    // Skupinovy filtr
    if (activeGroup === -1 && group >= 0) show = false;      // jen unikatni
    else if (activeGroup >= 0 && group !== activeGroup) show = false;  // konkretni skupina

    if (show) {{
      switch(activeSpecial) {{
        case 'best':     show = best; break;
        case 'unique':   show = group < 0; break;
        case 'dof':      show = dof; break;
        case 'blur':     show = sharp < 80; break;
        case 'sharp':    show = sharp > 200; break;
        case 'smile':    show = emo === 'smile'; break;
        case 'bad_face': show = emo === 'bad'; break;
        case 'top25':    show = score >= q75; break;
        case 'bot25':    show = score <= q25; break;
      }}
    }}

    c.classList.toggle('hidden', !show);
    if (show) vis++;
  }});
  document.getElementById('vis-count').textContent = vis;
}}

function filterCat(cat) {{
  activeCat = cat;
  applyFilters();
}}

function filterSpecial(type) {{
  activeSpecial = type;
  applyFilters();
}}

function filterScore(val) {{
  minScorePct = parseInt(val);
  document.getElementById('score-range-val').textContent = val + '%';
  applyFilters();
}}

// ── Razeni ────────────────────────────────────────────────────────────────────
function sortCards(by) {{
  const grid  = document.getElementById('grid');
  const cards = Array.from(grid.querySelectorAll('.card'));
  cards.sort((a,b) => {{
    if (by === 'score') return parseFloat(b.dataset.score) - parseFloat(a.dataset.score);
    if (by === 'sharp') return parseFloat(b.dataset.sharp) - parseFloat(a.dataset.sharp);
    if (by === 'group') {{
      const ga = parseInt(a.dataset.group);
      const gb = parseInt(b.dataset.group);
      if (ga === gb) return parseFloat(b.dataset.score) - parseFloat(a.dataset.score);
      if (ga < 0) return 1;
      if (gb < 0) return -1;
      return ga - gb;
    }}
    return a.dataset.name.localeCompare(b.dataset.name);
  }});
  cards.forEach(c => grid.appendChild(c));
  document.querySelectorAll('[id^=btn-]').forEach(b => b.classList.remove('active'));
  const el = document.getElementById('btn-'+by);
  if (el) el.classList.add('active');
}}

// ── Otevreni souboru ──────────────────────────────────────────────────────────
function openFile(path) {{
  // Prikaz photo_server.py musi bezet na pozadi (python photo_server.py)
  fetch('http://localhost:8765/open?path=' + encodeURIComponent(path))
    .then(r => r.text())
    .then(t => showNotif('Otevreno: ' + path.split('/').pop()))
    .catch(() => {{
      showNotif('[!] Server nebezi – spust: python photo_server.py', true);
    }});
}}

function showNotif(msg, err=false) {{
  const n = document.getElementById('notif');
  n.textContent = msg;
  n.style.borderColor = err ? '#c0392b' : '#e8a020';
  n.style.color = err ? '#c0392b' : '#e8a020';
  n.classList.add('show');
  setTimeout(() => n.classList.remove('show'), 3000);
}}
// ── Vyber fotek ───────────────────────────────────────────────────────────────
const selected = new Map(); // path -> name

function onCheck(cb) {{
  const path = cb.dataset.path;
  const name = cb.dataset.name;
  const card = cb.closest('.card');
  if (cb.checked) {{
    selected.set(path, name);
    card.classList.add('selected');
  }} else {{
    selected.delete(path);
    card.classList.remove('selected');
  }}
  updateSelBar();
}}

function updateSelBar() {{
  const bar   = document.getElementById('sel-bar');
  const label = document.getElementById('sel-count-label');
  const prev  = document.getElementById('sel-files-preview');
  const n     = selected.size;
  label.textContent = n + ' vybrano';
  const names = Array.from(selected.values()).slice(0, 5).join(', ');
  prev.textContent  = n > 5 ? names + ' ... +' + (n-5) + ' dalsich' : names;
  bar.classList.toggle('visible', n > 0);
}}

function selectVisible() {{
  document.querySelectorAll('.card:not(.hidden) .sel-cb').forEach(cb => {{
    cb.checked = true;
    selected.set(cb.dataset.path, cb.dataset.name);
    cb.closest('.card').classList.add('selected');
  }});
  updateSelBar();
}}

function clearSelection() {{
  selected.clear();
  document.querySelectorAll('.sel-cb').forEach(cb => {{
    cb.checked = false;
    cb.closest('.card').classList.remove('selected');
  }});
  updateSelBar();
}}

function resizeCards(val) {{
  document.getElementById('size-range-val').textContent = val + 'px';
  document.getElementById('grid').style.setProperty('--card-size', val + 'px');
}}
  if (selected.size === 0) return;
  const paths = Array.from(selected.keys());
  const dest  = prompt(
    'Zkopirovat ' + paths.length + ' fotek do slozky:\\n(zadej cilovy adresar)',
    'Z:\\\\Foto\\\\Vyber'
  );
  if (!dest) return;

  fetch('http://localhost:8765/copy', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ paths: paths, dest: dest }})
  }})
  .then(r => r.json())
  .then(data => {{
    showNotif(`Zkopírovano ${{data.copied}} / ${{data.total}} fotek do ${{dest}}`);
    if (data.errors && data.errors.length > 0) {{
      console.warn('Chyby pri kopirovani:', data.errors);
    }}
  }})
  .catch(() => showNotif('[!] Server nebezi – spust: python photo_server.py', true));
}}
</script>
</body>
</html>'''

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",            required=True)
    parser.add_argument("--output",           default="")
    parser.add_argument("--sort",             default="name", choices=["name","score","sharp"])
    parser.add_argument("--thumb-size",       type=int,   default=400)
    parser.add_argument("--dedup-thr",        type=float, default=0.92)
    parser.add_argument("--phash-thr",        type=float, default=0.83)
    parser.add_argument("--clip-model",       default="ViT-L/14", choices=["ViT-L/14","ViT-B/32"])
    parser.add_argument("--neg-weight",       type=float, default=0.7)
    parser.add_argument("--dof-peak-min",     type=float, default=120)
    parser.add_argument("--dof-ratio",        type=float, default=2.5)
    parser.add_argument("--blur-penalty-thr", type=float, default=40)
    parser.add_argument("--db",              default="")
    parser.add_argument("--session-name",    default="")
    parser.add_argument("--skip-files",      default="", help="Čárkou oddělené názvy souborů k přeskočení")
    parser.add_argument("--start-from",     default=0, type=int, help="Přeskoč prvních N souborů (pro debugging)")
    args = parser.parse_args()

    input_dir  = Path(args.input)
    output_dir = Path(args.output) if args.output else input_dir / "_dashboard"
    db_path    = Path(args.db) if args.db else Path(r"C:\ML\photo_library.db")
    skip_files = [s.strip() for s in args.skip_files.split(",") if s.strip()]

    score_photos(
        input_dir, output_dir, args.sort, args.thumb_size, args.dedup_thr,
        db_path=db_path, session_name=args.session_name,
        clip_model=args.clip_model, neg_weight=args.neg_weight,
        phash_threshold=args.phash_thr, dof_peak_min=args.dof_peak_min,
        dof_ratio=args.dof_ratio, blur_penalty_thr=args.blur_penalty_thr,
        skip_files=skip_files, start_from=args.start_from,
    )
