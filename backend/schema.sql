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
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_photos_session  ON photos(session_id);
CREATE INDEX IF NOT EXISTS idx_photos_score    ON photos(session_id, score DESC);
CREATE INDEX IF NOT EXISTS idx_photos_group    ON photos(session_id, group_id);
CREATE INDEX IF NOT EXISTS idx_photos_selected ON photos(session_id, selected);
