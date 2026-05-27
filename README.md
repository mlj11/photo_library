# Photo Library

Webová aplikace pro správu a prohlížení fotografií hodnocených AI modelem CLIP.
Skenuje složku s RAW/JPEG fotkami, ohodnotí je, detekuje duplicity a kategorie —
výsledky zobrazuje v interaktivním dashboardu.

---

## Spuštění

### Backend (FastAPI, port 8000)
```
python run_backend.py
```

### Frontend (React/Vite, port 5173)
```
cd frontend
npm run dev
```

Aplikace je pak dostupná na **http://localhost:5173**

---

## Skenování fotek – photo_score.py

Skript projde složku s fotkami, ohodnotí je pomocí CLIP a uloží výsledky do SQLite databáze.
Spouští se automaticky přes tlačítko **„+ Nový scan"** v GUI, nebo ručně z příkazové řádky:

```
python photo_score.py --input "Z:\Foto\RAW\2025_Tatry" --db "C:\ML\photo_library.db"
```

### Co skript dělá

| Krok | Popis |
|------|-------|
| Načtení CLIP | Stažení / načtení modelu ViT-L/14 (~900 MB, jen první spuštění) |
| Skenování | Každá fotka se zakóduje do 768-dim CLIP embeddingu |
| Kvalita | CLIP skóre = průměr pozitivních promptů − váha × průměr negativních |
| Kategorie | Porovnání s textovými prompty pro 6 kategorií |
| Ostrost & DOF | Laplaciánova variance v mřížce 4×4 bloků |
| Emoce | CLIP-based detekce úsměvu / špatného výrazu (jen pro portréty) |
| Deduplikace | CLIP + pHash podobnost s Union-Find pro tranzitivní skupiny |
| Thumbnail | JPEG náhled 400 px (konfigurovatelné) uložený do `_dashboard/_thumbs/` |
| Uložení | Výsledky zapsány do SQLite tabulek `sessions` + `photos` |

### CLI parametry

```
--input          Složka se zdrojovými fotkami (povinné)
--output         Výstupní složka pro náhledy (výchozí: input/_dashboard)
--db             Cesta k SQLite databázi (výchozí: C:\ML\photo_library.db)
--session-name   Název série v databázi (výchozí: název složky)
--sort           Řazení výsledků: name | score | sharp (výchozí: name)
--thumb-size     Velikost náhledů v px (výchozí: 400)
--dedup-thr      CLIP práh pro deduplikaci (výchozí: 0.92)
--phash-thr      pHash práh pro deduplikaci (výchozí: 0.83)
--clip-model     Model CLIP: ViT-L/14 | ViT-B/32 (výchozí: ViT-L/14)
--neg-weight     Váha negativních promptů (výchozí: 0.7)
--dof-peak-min   Min. ostrost pro detekci bokeh (výchozí: 120)
--dof-ratio      Poměr peak/median pro bokeh (výchozí: 2.5)
--blur-penalty-thr  Práh penalizace za rozmazání (výchozí: 40)
```

---

## Dashboard – přehled funkcí

### Seznam sérií (hlavní stránka)

- Přehled všech naskenovaných složek s počtem fotek a vybraných
- Tlačítko **⚙ Nastavení** – konfigurace parametrů skenování
- Tlačítko **+ Nový scan** – spuštění skenování nové složky
  - 📁 výběr složky přes průzkumník souborů
  - Automatické předvyplnění výstupní složky a názvu série
- Progress banner se zobrazí během skenování (přežije reload stránky)

### Dashboard série

#### Zobrazení
- **Mřížka karet** s náhledy, skóre, metrikami a badges
- **Slider velikosti karet** (150–600 px)
- Klik na náhled → **lightbox** s plným rozlišením (← → navigace, ESC zavře)
- Klik **„Otevřít v aplikaci"** → otevře originální soubor v systémovém prohlížeči

#### Řazení
| Volba | Popis |
|-------|-------|
| Název | Abecedně podle názvu souboru |
| Score | Celkové AI skóre |
| Ostrost | Laplaciánova variance (nejostřejší region) |
| Skupina | Skupiny deduplikace, unikátní vždy na konci, uvnitř skupiny best-first |
| Hodnocení | Hvězdičkové hodnocení uživatele |

Přepínač **↑ ASC / ↓ DESC** funguje pro všechny typy řazení.

#### Filtry

**Kategorie** (detekováno CLIP modelem):
| Zkratka | Popis |
|---------|-------|
| Portret-B | Blízký portrét, obličej vyplňuje záběr |
| Portret-V | Vzdálený portrét, celá postava viditelná |
| Krajina | Přírodní krajina bez lidí |
| Detail | Makro detail přírody, kamení, květin |
| Akce | Lidé v pohybu, lezení, turistika |
| Scena | Krajina s malými vzdálenými osobami |

**Speciální filtry:**
| Filtr | Popis |
|-------|-------|
| Nejlepší ve skupině | Fotka s nejvyšším skóre v každé deduplikační skupině |
| Unikátní | Fotky bez deduplikační skupiny |
| DOF/Bokeh | Detekovány s ostrým subjektem a rozmazaným pozadím |
| Rozmazané | Celkově rozmazané (sharp_center < 80) |
| Ostré | Vysoce ostré (sharp_center > 200) |
| Úsměv | Detekován úsměv (jen portréty) |
| Špatný výraz | Zavřené oči nebo špatný výraz |
| Top 25% / Spodních 25% | Podle celkového skóre |
| Vybrané | Fotky označené k exportu |

**Hodnocení (hvězdičky):**
- Vše / Nehodnocené / ★ až ★★★★★
- Operátor: **=** (přesně), **≥** (aspoň tolik), **≤** (nejvýš tolik)

**Skupina** (dropdown):
- Vše / Unikátní / konkrétní skupina gr.N
- Klávesy ← → pro přepínání skupin

**Min. score** – slider pro filtrování pod prahovou hodnotou

**Hledání** – fulltextové hledání v názvech souborů

#### Akce na fotkách
- **Hvězdičkové hodnocení** 1–5 (klik na hvězdičku, klik znovu = reset)
- **Poznámka** – krátký textový štítek (Enter uloží, Escape zruší)
- **Checkbox „Vybrat"** – označení k exportu

#### Výběr a export
- Tlačítka **Vybrat viditelné** / **Zrušit výběr**
- Spodní lišta se zobrazí při jakémkoliv výběru
- Export = zkopírování vybraných souborů do zvolené složky

---

## Nastavení skenování (⚙)

Všechna nastavení se ukládají do `backend/scan_config.json` a platí pro příští scan.

### CLIP model

| Parametr | Výchozí | Popis |
|----------|---------|-------|
| `clip_model` | ViT-L/14 | **ViT-L/14** – přesnější, ~900 MB, pomalejší načtení. **ViT-B/32** – rychlejší, ~350 MB, méně přesný. |

### Kvalita skóre

| Parametr | Výchozí | Rozsah | Popis |
|----------|---------|--------|-------|
| `neg_weight` | 0.70 | 0.3–1.2 | Váha negativních promptů (rozmazané, tmavé, špatná kompozice). Vyšší = přísnější penalizace. |

### Deduplikace & skupiny

| Parametr | Výchozí | Rozsah | Popis |
|----------|---------|--------|-------|
| `dedup_threshold` | 0.92 | 0.80–0.99 | Min. kosinová podobnost CLIP embeddingů pro zařazení do stejné skupiny. Nižší = větší skupiny. |
| `phash_threshold` | 0.83 | 0.65–0.95 | Min. podobnost perceptuálního hashe (256-bit). Nižší = toleruje větší pohyb osoby nebo objektu mezi záběry. |

Skupiny se tvoří s **Union-Find** (tranzitivně): pokud foto A~B a B~C, jsou všechna tři ve stejné skupině i když A s C přímo nesplní práh.

### Ostrost & DOF / bokeh

Detekce pracuje s **mřížkou 4×4 bloků** Laplaciánovy variance — najde nejostřejší region kdekoliv v obrazu, takže funguje i pro off-center kompozice (pravidlo třetin).

| Parametr | Výchozí | Rozsah | Popis |
|----------|---------|--------|-------|
| `dof_peak_min` | 120 | 30–400 | Minimální variance nejostřejšího bloku. Hodnoty pod tímto prahem = foto není dostatečně ostré ani lokálně. Snížit pro tmavší nebo méně kontrastní scény. |
| `dof_ratio` | 2.5 | 1.5–6.0 | Peak musí být X× ostřejší než medián bloků. Nižší = detekuje i jemný bokeh. Vyšší = jen výrazný bokeh/DOF. |
| `blur_penalty_thr` | 40 | 10–150 | Pod touto hodnotou variance dostane foto penalizaci za celkové rozmazání. Snížit pokud jsou správně rozmazané fotky penalizovány zbytečně. |

### Náhledy

| Parametr | Výchozí | Rozsah | Popis |
|----------|---------|--------|-------|
| `thumb_size` | 400 | 150–800 | Délka delší strany JPEG náhledu v pixelech. Větší = lepší kvalita v lightboxu, ale pomalejší scan a více místa na disku. |
| `sort` | name | name/score/sharp | Výchozí řazení výsledků v HTML dashboardu. |

---

## Technická architektura

```
photo-library/
├── backend/
│   ├── main.py          # FastAPI aplikace, všechny API endpointy
│   ├── database.py      # SQLite připojení, init_db()
│   ├── models.py        # Pydantic modely pro API
│   ├── scan_config.py   # Načtení/uložení scan_config.json
│   ├── scan_config.json # Uživatelská nastavení (auto-generováno)
│   ├── jobs.json        # Persistence běžících scanů (auto-generováno)
│   └── preview_cache/   # Cache preview JPEG z RAW souborů (auto-generováno)
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── SessionList.jsx  # Hlavní stránka, seznam sérií
│       │   └── Dashboard.jsx    # Dashboard série, mřížka fotek
│       └── components/
│           ├── PhotoCard.jsx    # Karta jedné fotky
│           ├── FilterBar.jsx    # Panel filtrů a řazení
│           ├── GroupNav.jsx     # Dropdown výběru skupiny
│           ├── Lightbox.jsx     # Fullscreen prohlížeč
│           ├── SelectionBar.jsx # Lišta výběru a exportu
│           └── SettingsModal.jsx# Modal nastavení skenování
├── photo_score.py       # AI skenovací skript (CLIP, pHash, DOF)
├── run_backend.py       # Spouštěč backendu (uvicorn, bez --reload)
└── photo_server.py      # Starý HTTP server pro otevírání souborů
```

### API endpointy

| Metoda | Endpoint | Popis |
|--------|----------|-------|
| GET | `/api/sessions` | Seznam všech sérií |
| POST | `/api/sessions` | Spuštění nového scanu |
| GET | `/api/sessions/{id}` | Detail série |
| DELETE | `/api/sessions/{id}` | Smazání série |
| GET | `/api/sessions/{id}/photos` | Fotky s filtry a řazením |
| GET | `/api/sessions/{id}/stats` | Statistiky série (histogram, kategorie, skupiny) |
| GET | `/api/sessions/{id}/export` | Export vybraných fotek |
| PATCH | `/api/photos/{id}` | Aktualizace fotky (rating, notes, selected…) |
| GET | `/api/jobs` | Seznam všech jobů skenování |
| GET | `/api/jobs/{id}` | Stav konkrétního jobu |
| GET | `/api/scan-config` | Načtení nastavení skenování |
| POST | `/api/scan-config` | Uložení nastavení skenování |
| GET | `/api/preview` | Fullres náhled (JPG/PNG přímo, RAW konverze s cache) |
| GET | `/api/thumb` | Malý náhled ze scan výstupu |
| GET | `/api/open` | Otevření souboru v systémovém prohlížeči |
| GET | `/api/pick-folder` | Nativní dialog výběru složky (tkinter) |
