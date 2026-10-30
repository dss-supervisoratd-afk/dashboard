# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

This is a customer-service BI system for AMN (Associação Abrigo do Marinheiro). It evolved from the self-contained dashboard `.resources/Painel de Atendimento.html`, which is git-ignored because it contains internal data. The UI text, code identifiers and comments are in Brazilian Portuguese; keep new code consistent with that. The README covers setup, roles and the import flow.

## Commands

```sh
docker compose up -d --build                  # full stack on :8080 (needs .env, see .env.example)

cd backend && pip install -r requirements.txt pytest
cd backend && pytest                          # all backend tests (SQLite, temp dir; see tests/conftest.py)
cd backend && pytest tests/test_api.py -k rbac
cd backend && uvicorn app.main:app --reload   # dev API on :8000 (SQLite dev.db; ADMIN_EMAIL/ADMIN_PASSWORD env creates first admin)
cd backend && python -m app.cli importar <arquivos-ou-pastas> [--autor email] [--reimportar]

cd frontend && npm run dev                    # :5173, proxies /api → :8000
cd frontend && npm run typecheck              # tsc --noEmit; there is no JS test suite
cd frontend && npm run build
```

Mutating API calls require the header `X-Requested-With: amn`, which is the CSRF guard in `app/main.py`. Tests use the `H` dict from `conftest.py`.

## Architecture

**Data model** (`backend/app/models.py`): `dim_dia` is a continuous calendar. `load.garante_dias` fills it between the first and last known day, and every fact joins it for month, weekday and day type. There are four fact tables: `f_ouvidoria`, `f_atendimento`, `f_servico` and `f_tempo`. Every fact row carries `lote_id` → `lote_importacao`. Day type is computed, not imported: weekends are always "Fim de semana", other days use the imported calendar label or "Normal".

**Semantic layer** (`backend/app/semantic.py`): this is the only place where BI SQL is built. `CONJUNTOS` declares each dataset's dimensions, measures and the global filters it responds to. The frontend sends `{conjunto, dims, medidas, filtros, ignorar, ordem, limite}` to `/api/bi/consulta`, or a batch of them to `/api/bi/lote`. Names are checked against the whitelist. Cross-filter rule: a global filter (setor/servico/atendente) applies only to datasets that have that column; `ignorar` lets a chart opt out (e.g. the sector list still shows all sectors while one is selected). Time averages (TME/TMD/TMA) are weighted by `n`. To add a metric, add a measure here; there is nothing to change in the router.

**Real sources** come from the GitHub repo `dss-supervisoratd-afk/Estatisticas-ATD` (`Relatórios/AAAA.MM/<tipo>/AAAA.MM.DD - Tipo - Relatório.ext`). `importers/sga.py` has dedicated readers for the three Novo SGA PDFs and the "Guichês - Tabela Consolidada" cadastro. It also parses the date and day type from file names. Its rules mirror `Scripts/gerar_relatorio_atendimento.py` in that repo. `importers/servico.py` is the single entry point (`analisa`/`grava`) shared by the HTTP routes and the CLI. It tries, in order: legacy HTML → SGA PDF → guichê cadastro → generic spreadsheet. `autoconfiavel` decides what bulk import may write without review. Facts keep the raw counter label in `atendente_origem`; `atendente` is the resolved display name, and importing the cadastro re-resolves history (`load.reaplica_nomes`).

**Import pipeline** (`backend/app/importers/`): `readers` turns CSV, XLSX, XLS and PDF into grids. `recognize` finds the header row, scores each schema in `schemas.py` (synonyms × value-type compatibility + filename hints), proposes a column mapping and converts rows. `separa` keeps the original row numbers for error messages. `load` writes the data with a **replace-by-day** policy: each file replaces its dataset's rows for the dates it contains, so re-importing is idempotent. Reverting a batch deletes its rows but does not restore the rows it replaced. The HTTP flow in `routers/imports.py` is `analisar` (upload + preview; the file is kept in `UPLOAD_DIR/<id>` for 24h) → `previa` (re-map) → `confirmar` (write). The legacy HTML goes through the same flow: `readers.extrai_raw_legado` → `load.carrega_legado`.

**Auth/RBAC** (`backend/app/security.py`): the session is a JWT in the httpOnly cookie `amn_sessao`. Roles map to permission strings in `PAPEIS`; endpoints use `Depends(exige("perm"))`. Google OAuth (authlib) uses Starlette's session cookie only for state; users are matched by `google_sub` or email, and are auto-provisioned only for `GOOGLE_ALLOWED_DOMAINS`. The schema is created with `create_all` at startup; there is no Alembic yet.

**Frontend** (`frontend/src/`): all dashboard state lives in the URL query string (`painel.tsx` `usePainelEstado`: de, ate, tipo, setor, servico, atendente, mmode, dia), so drill-downs are shareable links. `PainelLayout` (`shell.tsx`) loads `/api/bi/meta`, which provides the range, months, partial month, day types, sector ranking for stable colors and source coverage, and provides it via `PainelCtx`. Each tab in `views.tsx` issues one `useBI` batch and builds the charts with the components in `charts.tsx`. These are hand-written SVG components ported from the original HTML, with a single global tooltip in `tip.tsx`. Opening a day's detail sets `?dia=`, which renders `dia.tsx`. Permission-gated routes use `<Protegido perm=…>`.

## Conventions

- Theme: CSS tokens on `:root` in `styles.css`, which was extracted verbatim from the original HTML. Dark mode is defined under both `prefers-color-scheme` and `[data-theme="dark"]`; keep the two in sync. The choice is stored in `localStorage["amn-theme"]` and applied before the first paint in `index.html`.
- Sector colors are assigned by sector, not by chart position: the top 7 by all-time volume get `--s1..--s7` (`setorColor`).
- Variation thresholds: relevant ≥10%, sharp ≥20%. The current month is partial; don't compare it with closed months without the per-day average.
- "Ouvidorias por Situação" (one protocol per row, with associate names) is deliberately rejected; never import personal data.
