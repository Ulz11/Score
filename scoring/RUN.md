# Iveel × Dealy — Container Monitor

Палантираас санаа авсан, 5-сервистэй startup management платформ.
Goal-ыг хяналд аж нэг container (1B MNT) ба нэг agent монитор.

## Архитектур

5 сервис + frontend, бүгд нэг SQLite (`scoring.db`)-аар хамтран ажиллана.

```
team       :8011   workers / projects / tasks / KPI / auth
netdef     :8012   peer review / comments / mentions
money      :8013   meetings / binding votes / transactions
judge      :8014   audit / witness log (hash chain) / anomalies
container  :8015   THE GOAL — 1B MNT, milestones, scenarios, Excel I/O   ← NEW
web        :8010   static frontend (index.html, container.html, admin.html)
```

Бүх `id` нь UUID7. Лексикографоор үе үеийн дараалалтай — `ORDER BY id` нь
`ORDER BY created_at` -тай тэнцүү байж feed pagination-д ашиглах боломжтой.

## Constants — source of truth

`shared/constants.py` дотор бүх **frozen** мэдээлэл:

- `CONTAINER_TARGET = 1_000_000_000` MNT
- `MEMBERS` — 13 хүн + 1 `container_agent` (agent type, no login)
- `PROJECTS` — 7 sheet project
- `MILESTONES` — 27 milestone (id, date, track, owner handles, DoD, KPI, critical, expected_revenue)
- `TASK_ASSIGNMENTS` — (project, member) → task title + weight
- `SCENARIOS` — bear / base / bull, channel x order x AOV

Runtime-д **энэ файл өөрчлөгдөхгүй**. Зөвхөн DB дэх progress (status, completion %, inflows)
шинэчлэгдэнэ.

## Анхны setup

```bash
cd scoring/
pip install -e .                              # fastapi, uvicorn, openpyxl…
python -m shared.bootstrap --reset --iveel    # wipe + seed Iveel plan
python -m scripts.create_admin --handle admin --name "Admin"
python serve.py                               # boot all 5 services
```

Browser → http://127.0.0.1:8010/web/container.html

## API үндсэн endpoints

### Container (port 8015)

| Method | Path | Тайлбар |
|--------|------|--------|
| GET    | `/container`                    | Live state: target, filled, pace, monitor |
| GET    | `/container/inflows?limit=50`   | UUID7 cursor pagination |
| POST   | `/container/inflows`            | Add one inflow (auth required) |
| GET    | `/milestones`                   | 27 frozen milestones + progress |
| POST   | `/milestones/{id}/status`       | Update status / completion % |
| GET    | `/scenarios`                    | List 3 frozen scenario inputs |
| POST   | `/scenarios/simulate`           | Run bear/base/bull, persist snapshot |
| GET    | `/scenarios/runs?limit=20`      | Past simulation snapshots |
| POST   | `/excel/import` (admin)         | Upload XLSX of inflows |
| GET    | `/excel/export`                 | Download full state as XLSX |
| GET    | `/agent/report`                 | Single agent's at-a-glance health view |

### Excel import format

Sheet 1, header row 1:

```
occurred_at | amount_mnt | channel | milestone_id | note
```

- `channel` — one of `ecom_site_50off`, `zaisan_offline_70off`,
  `fb_messenger_chatbot`, `tourist_channel`, `limited_820_edition`
- `milestone_id` — `M01`..`M27` or blank
- `occurred_at` — ISO timestamp or Excel datetime

Unknown channels / milestones get reported as row-level errors but don't
fail the whole import.

## Хяналт ба audit

Бүх container write (inflow, milestone status, scenario run, Excel sync)
нь `judge_witness_log` дотор hash chain-аар бичигдэнэ. Урьдынхаа hash-аар
гинж үүсгэдэг учраас бүх log-ыг өөрчилөхгүйгээр нэг ч row нь засагдашгүй.

`judge` сервис `/audits` тогтмол log-уудыг хяналдаг — collusion, vote
rigging, KPI gaming.

## Тестүүд

```bash
pytest tests/                # бүх 53 тест
pytest tests/test_container.py -v   # зөвхөн container service
```

## Production-д руу гарах

1. `HOST=0.0.0.0 python serve.py` LAN-аас хүртэх
2. `CORS_ORIGIN` нь жинхэнэ HTTPS origin
3. `--iveel` seed-ыг зөвхөн анх удаагаа (idempotent ч гэсэн)
4. Admin password rotate `python -m scripts.create_admin --handle admin ...`
5. WAL backup стратеги — sqlite-н WAL файлуудыг агшинд хуулах
