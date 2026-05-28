import json
from pathlib import Path

_FILE = Path(__file__).parent / "scan_config.json"

DEFAULTS = {
    "clip_model":       "ViT-L/14",
    "thumb_size":       400,
    "sort":             "name",
    "dedup_threshold":  0.92,
    "phash_threshold":  0.83,
    "neg_weight":       0.7,
    "dof_peak_min":     120,
    "dof_ratio":        2.5,
    "blur_penalty_thr": 40,
    "skip_files":       [],
}

def load() -> dict:
    if _FILE.exists():
        try:
            saved = json.loads(_FILE.read_text(encoding="utf-8"))
            cfg = {**DEFAULTS, **saved}
            if not isinstance(cfg.get("skip_files"), list):
                cfg["skip_files"] = []
            return cfg
        except Exception:
            pass
    return dict(DEFAULTS)

def save(data: dict) -> dict:
    cfg = {k: data.get(k, v) for k, v in DEFAULTS.items()}
    if not isinstance(cfg.get("skip_files"), list):
        cfg["skip_files"] = []
    _FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return cfg