# Photo Library – Projektová specifikace pro Claude Code

## Přehled

Aplikace pro správu a prohlížení fotografií s AI hodnocením.
Existující `photo_score.py` skenuje složku s RAW fotkami (Sony ARW), hodnotí je
pomocí CLIP modelu a ukládá výsledky do SQLite databáze.
Tato aplikace poskytuje webový dashboard pro prohlížení, filtrování a výběr fotek
bez nutnosti znovu skenovat.

---

## Stack

- **Backend**: Python, FastAPI, SQLite (přes SQLModel nebo plain sqlite3)
- **Frontend**: React + Tailwind CSS (nebo plain HTML/JS pokud jednodušší)
- **DB**: SQLite – `photo_library.db`
- **Existující skripty**: `photo_score.py` (scanner), `photo_server.py` (file opener)

---

## Databázové schema

```sql
-- Sezení = jedna naskenovaná složka fotek
CREATE TABLE sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,           -- název série (např. "2025_Tatry")
    input_dir    TEXT NOT NULL,           -- cesta ke složce se zdrojovými fotkami
    thumb_dir    TEXT NOT NULL,           -- cesta ke složce s náhledy
    scanned_at   TEXT NOT NULL,           -- ISO datetime
    total_photos INTEGER DEFAULT 0,
    notes        TEXT DEFAULT ''
);

-- Fotky
CREATE TABLE photos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES sessions(id),

    -- Soubor
    name            TEXT NOT NULL,        -- název souboru (DSC_001.ARW)
    path            TEXT NOT NULL,        -- absolutní cesta k originálu
    thumb           TEXT NOT NULL,        -- relativní cesta k náhledu (_thumbs/xxx.jpg)

    -- AI scores
    score           REAL DEFAULT 0,       -- celkové skóre
    clip_score      REAL DEFAULT 0,       -- CLIP quality score
    sharp_center    REAL DEFAULT 0,       -- ostrost středu
    sharp_edges     REAL DEFAULT 0,       -- ostrost okrajů
    sharp_total     REAL DEFAULT 0,       -- celková ostrost
    dof             INTEGER DEFAULT 0,    -- 1 = záměrné bokeh/DOF
    comp_score      REAL DEFAULT 0,       -- kompoziční skóre
    category        TEXT DEFAULT '',      -- portret_blizky|portret_vzdaleny|krajina|detail|akce|scena
    emotion         TEXT DEFAULT '',      -- smile|neutral|bad|''
    face_score      REAL DEFAULT 0,

    -- Skupiny deduplikace
    group_id        INTEGER DEFAULT -1,   -- -1 = unikátní, 0+ = skupina
    best_in_group   INTEGER DEFAULT 0,    -- 1 = nejlepší ve skupině

    -- Uživatelská data (editovatelné bez rescanu)
    selected        INTEGER DEFAULT 0,    -- 1 = vybráno do další fáze
    user_category   TEXT DEFAULT '',      -- manuální překategorizace
    user_rating     INTEGER DEFAULT 0,    -- hvězdičky 0-5
    notes           TEXT DEFAULT '',      -- poznámky k fotce
    exported        INTEGER DEFAULT 0,    -- 1 = již exportováno
    export_path     TEXT DEFAULT '',      -- kam bylo exportováno

    created_at      TEXT NOT NULL
);

-- Index pro rychlé dotazy
CREATE INDEX idx_photos_session ON photos(session_id);
CREATE INDEX idx_photos_score   ON photos(session_id, score DESC);
CREATE INDEX idx_photos_group   ON photos(session_id, group_id);
CREATE INDEX idx_photos_selected ON photos(session_id, selected);
```

---

## API endpoints (FastAPI)

### Sessions
```
GET    /api/sessions              – seznam všech sezení
POST   /api/sessions              – vytvoř nové sezení (spustí scan)
GET    /api/sessions/{id}         – detail sezení
DELETE /api/sessions/{id}         – smaž sezení
```

### Photos
```
GET    /api/sessions/{id}/photos  – seznam fotek s filtrováním
  Query params:
    sort      = score|name|sharp|group|rating  (default: name)
    order     = asc|desc
    category  = all|portret_blizky|portret_vzdaleny|krajina|detail|akce|scena
    group_id  = -2 (vše) | -1 (unikátní) | 0+ (konkrétní skupina)
    special   = all|best|unique|dof|blur|sharp|smile|bad_face|top25|bot25|selected
    min_score = 0.0–1.0
    search    = string (hledání v názvu)

PATCH  /api/photos/{id}           – update uživatelských dat
  Body: { selected, user_category, user_rating, notes }

POST   /api/sessions/{id}/export  – zkopíruj vybrané fotky
  Body: { dest_dir: string, only_selected: bool }
```

### Stats
```
GET    /api/sessions/{id}/stats   – statistiky sezení
  Vrátí: score distribution, category counts, group counts, selected count
```

### Files
```
GET    /api/open?path=...         – otevři soubor ve Windows (os.startfile)
GET    /api/thumb?path=...        – servuj náhled (nebo přes static files)
```

---

## Úprava photo_score.py

Přidej do existujícího `photo_score.py` funkci `save_to_db()` která po dokončení
scoringu uloží výsledky do SQLite:

```python
def save_to_db(results: list, input_dir: Path, output_dir: Path, db_path: Path):
    import sqlite3
    from datetime import datetime

    conn = sqlite3.connect(str(db_path))
    c    = conn.cursor()

    # Vytvoř tabulky pokud neexistují
    c.executescript(SCHEMA_SQL)  # obsah schema.sql

    # Vlož session
    c.execute("""
        INSERT INTO sessions (name, input_dir, thumb_dir, scanned_at, total_photos)
        VALUES (?, ?, ?, ?, ?)
    """, (input_dir.name, str(input_dir), str(output_dir),
          datetime.now().isoformat(), len(results)))
    session_id = c.lastrowid

    # Vlož fotky
    for r in results:
        c.execute("""
            INSERT INTO photos (
                session_id, name, path, thumb,
                score, clip_score, sharp_center, sharp_edges, sharp_total,
                dof, comp_score, category, emotion, face_score,
                group_id, best_in_group, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            session_id, r["name"], r["path"], r["thumb"],
            r["score"], r["clip"], r["sharp_c"], r["sharp_e"], r["sharp_t"],
            1 if r["dof"] else 0, r["comp"], r["category"],
            r["emotion"], r["face_score"],
            r["group"], 1 if r["best_in_group"] else 0,
            datetime.now().isoformat()
        ))

    conn.commit()
    conn.close()
    return session_id
```

---

## Frontend (React dashboard)

### Stránky
```
/                    – seznam sezení (session list)
/session/:id         – dashboard konkrétního sezení
/session/:id/export  – export dialog
```

### Session list (`/`)
- Tabulka sezení: název, datum, počet fotek, počet vybraných
- Tlačítko "Nový scan" → dialog pro zadání složky
- Klik na sezení → přejde na dashboard

### Dashboard (`/session/:id`)
Layout:
```
┌─────────────────────────────────────────────┐
│ HEADER: název série, stats, controls        │
│ ─────────────────────────────────────────── │
│ SIDEBAR (volitelný):                        │
│   - Score histogram                         │
│   - Category breakdown (pie/bar)            │
│   - Skupiny navigator                       │
│ ─────────────────────────────────────────── │
│ GRID: fotky s náhledy, badges, checkbox     │
│ ─────────────────────────────────────────── │
│ SELECTION BAR (fixed bottom): export CTA   │
└─────────────────────────────────────────────┘
```

### Karta fotky
```
┌──────────────────────┐
│   [náhled fotky]     │  ← klik = otevřít originál
│                      │
├──────────────────────┤
│ 0.7234    ████░░     │  ← score + bar
│ DSC_001.ARW          │
│ clip:0.71 sh:234 +.12│  ← metriky
│ [krajina][sharp]     │  ← badges
│ ★★★☆☆  [poznámka]   │  ← user rating + notes
│ ☐ Vybrat             │  ← checkbox
└──────────────────────┘
```

---

## Instalace a spuštění

```bash
# Backend
pip install fastapi uvicorn sqlmodel

# Spuštění
uvicorn main:app --reload --port 8000

# Frontend (pokud React)
cd frontend
npm install
npm run dev
```

---

## Adresářová struktura

```
photo-library/
├── backend/
│   ├── main.py          – FastAPI app
│   ├── models.py        – SQLModel modely
│   ├── database.py      – DB inicializace
│   ├── schema.sql       – SQL schema
│   └── photo_library.db – SQLite DB
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── pages/
│   │   │   ├── SessionList.jsx
│   │   │   └── Dashboard.jsx
│   │   └── components/
│   │       ├── PhotoCard.jsx
│   │       ├── FilterBar.jsx
│   │       ├── GroupNav.jsx
│   │       └── SelectionBar.jsx
│   └── package.json
├── photo_score.py       – existující scanner (upravit pro DB)
└── photo_server.py      – existující file opener
```

---

## Prioritní pořadí implementace

1. **DB schema + photo_score.py úprava** – uložení výsledků do DB
2. **FastAPI backend** – základní CRUD + filtry
3. **Session list** – přehled naskenovaných sérií
4. **Dashboard grid** – zobrazení fotek s filtry
5. **Interaktivita** – checkbox, rating, notes, group navigation
6. **Export** – kopírování vybraných fotek

---

## Poznámky

- Náhledy jsou JPEG soubory generované při scanu, uložené v `{input_dir}/_dashboard/_thumbs/`
- Originály jsou RAW soubory (ARW) na NAS – přístup přes síťový disk (Z:\)
- Backend běží lokálně na Windows PC
- Není potřeba autentizace – lokální aplikace
- DB path: konfigurovatelný, default `C:\ML\photo_library.db`
