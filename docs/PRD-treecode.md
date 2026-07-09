# PRD — `treecode`

> Plugin Claude Code per costruire e mantenere un **albero distribuito di CLAUDE.md**: root snello come mappa + file annidati lazy per-modulo, con toolchain deterministica per cap/idempotenza/drift.
> Documento di specifica destinato a essere passato a Claude Code per l'implementazione.

**Versione PRD:** 0.1 · **Nome plugin/repo:** `treecode` · **Marketplace:** `iu3qez-tools` · **Target:** Claude Code ≥ 2.1.4 (hooks/InstructionsLoaded/`paths:`).

> **Lingua di consegna (MUST).** Il repository sarà **pubblico**: tutti gli artefatti del plugin vanno scritti **in inglese** — `README.md`, `SKILL.md`, frontmatter e corpo dei comandi, definizioni degli agent, `description` in `plugin.json`/`marketplace.json`, commenti e docstring in `treemap.py`, messaggi CLI/report, testo degli hook. Questo PRD è in italiano solo come documento interno di specifica; l'implementazione e la documentazione del plugin sono interamente in inglese. Distinto dal parametro runtime `generated_language` (§8), che governa invece la lingua del contenuto scritto nei CLAUDE.md dei **repo target dell'utente** (default `en`, configurabile).

---

## 1. Problema e obiettivo

Claude Code parte ogni sessione con context window pulita e zero conoscenza della struttura del codice. Le alternative sono due: esplorare da zero (lento, "ravana" nel codice) o partire da una mappa persistita. Il plugin ufficiale `claude-md-management` **audita la qualità** di CLAUDE.md esistenti e cattura learning, ma **non architetta l'albero distribuito** che è il vero rimedio.

**Obiettivo.** Generare e sincronizzare in modo idempotente una gerarchia di CLAUDE.md dove:
- il **root** è una mappa scannabile (<80 righe): dove stanno le cose + puntatori ai moduli;
- ogni **modulo** ha un CLAUDE.md annidato (30–60 righe) con scopo, astrazioni, dipendenze, gotcha;
- il contenuto generato è racchiuso in marker block e **non tocca** mai il testo scritto a mano;
- un comando di **drift** segnala divergenze tra mappa documentata e struttura reale.

## 2. Non-obiettivi

- **Non** duplicare la auto memory. La auto memory (`MEMORY.md` + topic file) gestisce i learning volatili (comandi scoperti, quirk, correzioni). Questo plugin scrive **solo struttura stabile** (architettura, confini, responsabilità).
- **Non** essere un linter di qualità della prosa (è ciò che fa già `claude-md-improver`); integrazione sì, sovrapposizione no.
- **Non** auto-committare. Mai. Genera → report → l'utente committa.
- **Non** gestire regole comportamentali "quando editi X fai Y": quelle vanno in `.claude/rules/` path-scoped (vedi §9, opzionale).

## 3. Invarianti critici (MUST — non negoziabili)

Questi vincoli derivano dalla meccanica di caricamento di Claude Code e sono la ragione d'essere del plugin. L'implementazione DEVE rispettarli.

1. **Usare CLAUDE.md annidati reali in sottodirectory.** Si caricano on-access (lazy) solo quando Claude legge un file in quella sottocartella. Questo è il meccanismo che dà consapevolezza strutturale senza bloat.
2. **MAI cablare l'albero via `@path import` dal root.** Gli import si caricano **al lancio**: replicherebbero esattamente il bloat che il plugin vuole eliminare. L'annidamento in sottodirectory è l'**unico** meccanismo realmente lazy.
3. **Idempotenza tramite marker block.** Il generato vive tra marker; tutto ciò che sta fuori è testo umano e non va toccato. Rilanci ripetuti devono produrre lo stesso output e preservare gli edit manuali.
4. **Root = mappa, non listing.** Root sotto ~80 righe (file >200 righe riducono l'aderenza). Niente elenchi di file: solo "dove stanno le cose" + puntatori ai moduli.
5. **Nested = 30–60 righe descrittive.** Scopo/responsabilità, astrazioni e interfacce chiave, dipendenze in/out, convenzioni, gotcha. Zero file listing.
6. **Rispettare `.gitignore` e `.claudeignore`.** Mai scrivere in directory ignorate, generate, `node_modules/`, `.git/`, build output.
7. **Il root sopravvive al compaction** (riletto da disco), i **nested no** (si ricaricano alla successiva lettura in quella sottodir). Non assumere che i nested siano sempre in contesto.

## 4. Utenti e contesto d'uso

Sviluppatore singolo/piccolo team su repo Python (FastAPI/`pyproject.toml`) e SvelteKit (adapter-static), monorepo e repo singoli. Detector estendibili per altri ecosistemi (Node, Go, Rust). Installazione via GitHub personale → marketplace privato → `/plugin install`.

## 5. Architettura del plugin

Layout standard Claude Code (cartelle auto-discovered):

```
treecode/
├── .claude-plugin/
│   ├── plugin.json              # manifest del plugin (required)
│   └── marketplace.json         # catalogo — richiesto per l'installabilità (source: "./")
├── commands/
│   ├── map-tree.md              # /map-tree  (build/sync)
│   └── map-drift.md             # /map-drift (check-only)
├── skills/
│   └── tree-mapper/
│       └── SKILL.md             # workflow orchestrante (lazy, on-demand)
├── agents/
│   └── module-cartographer.md   # subagent a contesto ridotto (opzionale)
├── hooks/
│   └── hooks.json               # PostToolUse cap-guard + InstructionsLoaded log
├── scripts/
│   └── treemap.py               # helper deterministico (stdlib-only)
├── README.md
└── LICENSE                      # MIT
```

**`plugin.json`** (campi: `name`, `version`, `description`, `author`, `homepage`, `license`). Gli slash command, agent e skill sono scoperti dalle rispettive cartelle. La skill è registrata come `treecode:tree-mapper`.

**Path degli script:** invocare sempre via `${CLAUDE_PLUGIN_ROOT}/scripts/treemap.py`, mai path relativi al cwd.

### 5.1 Divisione deterministico / semantico

Principio: la parte meccanica e ripetibile la fa uno **script Python** (stdlib-only, nessuna dipendenza da installare); la parte che richiede giudizio la riempie il **modello**.

- **Script (`treemap.py`)** — walk dell'albero (rispetta `.gitignore`), boundary detection, grafo delle dipendenze (best-effort), validazione cap, diff di drift, lettura/scrittura del marker block, emissione JSON. Sotto-comandi: `scan`, `check`, `write-block`, `read-block`.
- **Modello (skill)** — per ciascun modulo individuato, esplora i sorgenti e compila i campi semantici (scopo, gotcha, convenzioni) che uno script non può inferire, poi delega allo script la scrittura idempotente nel marker.

## 6. Componenti — specifiche di dettaglio

### 6.1 Skill `tree-mapper` (`skills/tree-mapper/SKILL.md`)

Trigger: invocata dai comandi, o quando l'utente chiede "mappa l'albero del codebase / genera i CLAUDE.md di modulo". `description` concisa e specifica (name+description caricati all'avvio; SKILL.md completo lazy).

Workflow:
1. Eseguire `treemap.py scan --json` → ottiene moduli, confini, grafo deps, violazioni cap, stato marker esistenti.
2. Presentare all'utente il **piano**: elenco moduli da creare/aggiornare, con conteggio. Chiedere conferma se >K file impattati (default K=15).
3. Per ogni modulo (opz. via subagent `module-cartographer` per non inquinare il contesto): leggere i sorgenti chiave, compilare il template (§7.1), scrivere via `treemap.py write-block` (solo dentro il marker).
4. Aggiornare la mappa root via marker `treecode:map` (§7.2).
5. Eseguire `treemap.py check` → report finale (moduli scritti, cap OK, drift residuo).
6. **Non** committare; stampare il set di file modificati e suggerire il commit.

### 6.2 Comandi

- **`/map-tree [path]`** — build/sync completo (o limitato a `path`). Idempotente. Flag: `--dry-run` (solo piano, nessuna scrittura), `--force` (rigenera anche moduli invariati), `--generic` (disabilita i detector stack-aware).
- **`/map-drift [path]`** — solo audit: esegue `treemap.py check`, stampa la tabella di drift, **nessuna scrittura**. Exit code ≠ 0 su drift (CI-friendly).

### 6.3 Helper `treemap.py`

Requisiti: Python 3.11+, **solo stdlib** (portabile, nessun `pip install`). Sotto-comandi:

- `scan` → JSON `{modules:[{path, kind, source_count, depends_on[], used_by[], has_manual_content, block_present, over_cap}], root_map, ignored[]}`.
- `check` → JSON `{drift:{new[], renamed[], removed[], dead_pointers[], orphan_nested[], cap_violations[]}}`, exit 1 se drift non vuoto.
- `write-block --path <dir> --content <file|stdin>` → inserisce/rimpiazza **solo** il blocco tra i marker; crea il CLAUDE.md se assente preservando eventuale testo umano; verifica cap post-scrittura.
- `read-block --path <dir>` → estrae il blocco corrente (per diff).

Config letta da `treemap.config.json` (§8); default hardcoded se assente.

### 6.4 Subagent `module-cartographer` (opzionale)

`memory: project`, `fork_safe: true`, model `haiku` o `sonnet`. Scopo: esplorare **un** modulo con contesto focalizzato e restituire il template compilato, senza gonfiare il contesto della sessione principale. La skill può forkarne N in parallelo su moduli indipendenti.

### 6.5 Hook (`hooks/hooks.json`)

Schema keyed-object canonico (eventi: `PostToolUse`, `InstructionsLoaded`).

- **`PostToolUse` su `Write|Edit`** con matcher sul filename `CLAUDE.md` → esegue `treemap.py check --cap-only` e **avvisa** (fail-open) se il file supera il cap. Non blocca di default per non creare frizione; modalità `strict` opzionale (blocca) via config.
- **`InstructionsLoaded`** (tutti i `load_reason`) → logging opzionale di quali CLAUDE.md vengono caricati, quando e perché. Utile per debug del lazy-loading. **Off di default**, attivabile in config.

## 7. Formati

### 7.1 Template nested (`<module>/CLAUDE.md`)

Contenuto generato **in inglese** (i CLAUDE.md sono spesso team-shared/code-adjacent), racchiuso nei marker:

```markdown
<!-- BEGIN treecode (auto) — do not edit inside this block -->
# <module-name> — <one-line purpose>

Responsibility: <what this module owns; what it must NOT do>
Key abstractions: <classes/interfaces/entrypoints that matter>
Depends on: <internal modules it imports>
Used by: <internal modules that import it>
External deps of note: <libs with non-obvious usage>
Conventions: <module-local rules>
Gotchas: <non-obvious behaviors, footguns>
<!-- END treecode (auto) -->
```

Testo umano sopra/sotto il blocco: **mai** toccato.

### 7.2 Mappa root (blocco in `./CLAUDE.md`)

```markdown
<!-- BEGIN treecode:map (auto) -->
## Codebase map
- `src/api/`     — HTTP handlers        → src/api/CLAUDE.md
- `src/core/`    — domain logic          → src/core/CLAUDE.md
- `src/db/`      — persistence, models   → src/db/CLAUDE.md
- `migrations/`  — Alembic revisions     → migrations/CLAUDE.md
<!-- END treecode:map (auto) -->
```

### 7.3 Report di drift (stdout, tabellare)

Colonne: `type` (new/renamed/removed/dead-pointer/orphan/cap), `path`, `detail`, `suggested-action`.

## 8. Configurazione (`treemap.config.json`, root del repo target)

```json
{
  "caps": { "root": 80, "nested": 60, "hard_max": 200 },
  "boundaries": {
    "min_sources": 3,
    "max_depth": 4,
    "package_markers": ["pyproject.toml","package.json","go.mod","Cargo.toml","pom.xml"],
    "framework_dirs": ["src/routes","src/lib","app/api","src/app"],
    "monorepo_globs": ["packages/*","apps/*","libs/*"]
  },
  "ignore_globs": ["**/node_modules/**","**/.venv/**","**/dist/**","**/build/**","**/__pycache__/**"],
  "markers": { "module": "treecode", "root": "treecode:map" },
  "generated_language": "en",
  "hooks": { "cap_guard": "warn", "instructions_loaded_log": false },
  "stack_aware": true
}
```

## 9. Boundary detection — euristica

1. **Package markers**: ogni dir con `pyproject.toml`/`package.json`/`go.mod`/… è un modulo.
2. **Convenzioni framework**: `src/routes`, `src/lib` (SvelteKit); `app/api`, `src/app` (Next); dir sotto `src/` con ≥ `min_sources` sorgenti.
3. **Monorepo**: `packages/*`, `apps/*`, `libs/*` → un modulo ciascuno.
4. **Merge**: dir troppo piccole (< `min_sources`) collassano nel parent.
5. **Depth cap**: non scendere oltre `max_depth`.
6. **Grafo deps**: parsing best-effort di import/require dove economico (Python `ast`, JS/TS regex sugli import); altrimenti campo vuoto. Mai bloccare su parsing fallito.
7. Con `stack_aware=false` (o `--generic`): solo package markers + soglia sorgenti, nessuna euristica framework.

### 9.1 (Opzionale) Generazione `.claude/rules/`

Flag `--with-rules`: per moduli con vincoli d'uso ricorrenti, generare regola path-scoped in `.claude/rules/<module>.md` (nested CLAUDE.md = *cos'è* il modulo; rule = *come* si tocca). Anch'esse marker-delimited e idempotenti. Default: off.

## 10. Edge case

- CLAUDE.md preesistente senza marker → creare il blocco in testa/coda senza alterare il resto; non assumere ownership del file.
- Blocco marker corrotto/duplicato → rifiutare la scrittura, segnalare, non indovinare.
- Modulo rinominato → drift `renamed` (match per contenuto/heuristica), suggerire spostamento, non cancellare in automatico.
- Nested orfano (modulo rimosso) → drift `orphan`, suggerire rimozione, non cancellare senza conferma.
- Repo enorme → `--dry-run` e conferma sopra soglia; forkare subagent per parallelizzare.
- Symlink/monorepo con worktree → non seguire symlink fuori dal repo root.
- `generated_language` diverso da default → il modello scrive i campi nella lingua richiesta, i marker restano invariati.

## 11. Criteri di accettazione (testabili)

1. Su un repo di test (Python `src/` + SvelteKit `frontend/`) `/map-tree` crea nested CLAUDE.md nei moduli attesi e un blocco mappa nel root, tutti sotto cap.
2. Rilancio di `/map-tree` senza modifiche al codice → **zero diff** (idempotenza).
3. Testo umano aggiunto fuori dai marker → sopravvive a un rilancio.
4. Nessun `@path import` viene mai scritto per cablare l'albero.
5. `/map-drift` su repo con un modulo rinominato → exit ≠ 0 e riga `renamed` corretta.
6. Hook `cap_guard=warn` → editando manualmente un CLAUDE.md oltre cap compare l'avviso, la scrittura **non** è bloccata.
7. `treemap.py` gira senza alcun `pip install` su Python 3.11 pulito.
8. Nessun file in `ignore_globs`/`.gitignore` viene creato o modificato.
9. `/plugin install` da marketplace privato registra comandi, skill e hook; `treecode:tree-mapper` compare tra le skill.

## 12. Packaging & install

**Due file JSON, ruoli distinti** (entrambi in `.claude-plugin/`):
- `plugin.json` — manifest del singolo plugin (la cosa che si installa).
- `marketplace.json` — catalogo alla root del repo, letto da `/plugin marketplace add`. **Richiesto**: senza, il repo non è aggiungibile come marketplace e nulla è installabile. Per repo mono-plugin, referenzia il plugin nello stesso repo con `source: "./"`.

**`marketplace.json`:**
```json
{
  "name": "iu3qez-tools",
  "owner": { "name": "<user>", "url": "https://github.com/<user>" },
  "plugins": [
    {
      "name": "treecode",
      "source": "./",
      "description": "Distributed, lazy-loaded CLAUDE.md tree for Claude Code: lean root map + per-module nested files, idempotent, with drift detection and cap enforcement.",
      "version": "0.1.0"
    }
  ]
}
```

**Install:**
```
/plugin marketplace add <user>/treecode
/plugin install treecode@iu3qez-tools
```

**Vincoli/gotcha da rispettare:**
- Il nome nel `@<marketplace>` è il `name` del marketplace (`iu3qez-tools`), **non** il nome del repo.
- `source: "./"` funziona solo se il marketplace è aggiunto via git (`owner/repo`), non via URL diretto al JSON.
- Versionare esplicitamente `version` in entrambi i file; se assente, viene usato lo SHA del commit.
- **Non** spedire un CLAUDE.md dentro la cartella del plugin: non è un componente riconosciuto e viene ignorato. Le istruzioni del plugin viaggiano solo via `skills/*/SKILL.md`.
- Skill e comandi sono namespaced: `treecode:tree-mapper`, `/treecode:map-tree`.
- Pre-push: `claude plugin validate .` (o `/plugin validate .`) valida `marketplace.json` (schema, nomi duplicati, path traversal, mismatch versione) e ogni `plugin.json` referenziato.
- README: quickstart, i 7 invarianti (§3) in evidenza, tabella comandi, esempio prima/dopo. LICENSE MIT.
- **Discoverability** (`treecode` è poco usato nell'ecosistema Claude Code ma collide con termini di scientific computing — N-body/Barnes-Hut treecode, tree codes): differenziare via `description` e metadati. GitHub *About* = tagline estesa: "Build and maintain a distributed CLAUDE.md tree — a lean root map plus lazy, per-module nested CLAUDE.md files — so Claude Code starts each session already knowing your codebase structure instead of re-exploring it. Idempotent marker blocks, line-cap enforcement, and drift detection; complements auto memory instead of duplicating it." GitHub *topics*: `claude-code`, `claude-code-plugin`, `claude-md`, `codebase-map`, `project-memory`, `developer-tools`.

## 13. Ordine di build (milestone)

- **M1** — `treemap.py` (`scan`/`check`/`read-block`/`write-block`) + test unit su un repo fixture. È il cuore deterministico.
- **M2** — Skill `tree-mapper` + comando `/map-tree` (build idempotente, marker, cap).
- **M3** — `/map-drift` + report + exit code.
- **M4** — Hook `hooks.json` (cap-guard warn; InstructionsLoaded log off).
- **M5** — Subagent `module-cartographer` + fork parallelo.
- **M6** — `--with-rules`, `--generic`, packaging, README, marketplace entry.

## 14. Domande aperte (da decidere in implementazione)

1. **Stato drift**: stateless (ricalcolo dalla struttura a ogni run) vs lock file (`.claude-plugin/treemap.lock.json`). Default proposto: stateless, con lock opzionale per rename affidabili.
2. **Aggressività del parsing dipendenze**: solo Python `ast` + regex JS/TS, o estendere? Partire minimale.
3. **InstructionsLoaded log** on/off di default (proposto: off, opt-in).
4. Lingua del contenuto generato di default (proposto: `en`; l'utente può forzare `it`).
