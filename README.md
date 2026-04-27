# R3

R3 (описан в [PROMPT.md](PROMPT.md)) — веб‑приложение вокруг уже развёрнутого [Redmine](https://www.redmine.org/): «протухшие» назначенные задачи, разбивка на подзадачи, Task Wizard, оценка сложности, учёт в Redmine, опциональные подсказки LLM, LDAP и роли. Стек: **FastAPI + SQLAlchemy (async) + PostgreSQL**, **React (Vite) + Tailwind**, **docker-compose**.

## Быстрый старт (локально)

1. **Бэкенд:** `cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && export DATABASE_URL=postgresql+asyncpg://r3:r3@localhost:5432/r3` (смените `SECRET_KEY`), затем `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`.
2. **Фронтенд:** `cd frontend && npm install && npm run dev` (прокси `/api` на `localhost:8000` см. [frontend/vite.config.ts](frontend/vite.config.ts)).
3. **Вход:** первый старт создаёт учётку `admin` / `changeme` (см. [backend/app/core/config.py](backend/app/core/config.py)).
4. **Redmine и ИИ** задаёт администратор в UI «Настройки» (нужен URL и API key Redmine; ключи `openai` / `gemini` / `deepseek` — по пулу с round-robin).
5. **Свой id в Redmine** укажите в профиле (PATCH `redmine_user_id` через тот же UI, что в Workbench/Wizard, пока без отдельной страницы «Профиль»).
6. **Роли:** `superadmin`, `admin`, `product_manager`, `user` — в БД ([backend/app/core/roles.py](backend/app/core/roles.py)). PM видит [PM Backlog](frontend/src/pages/PmBacklog.tsx) и [Статистику](frontend/src/pages/Stats.tsx).

## Docker

```bash
export R3_SECRET_KEY="$(openssl rand -hex 32)"
docker compose up --build
```

- **HTTP:** порт 80 (фронт) → `http://localhost`, API проксируется с `/api` на `api:8000`.
- **Прямой API:** `http://localhost:8000` (см. маппинг портов в [docker-compose.yml](docker-compose.yml)).
- **HTTPS (без certbot):** порт 4443, при первом старте контейнер `web` генерирует CA и сертификат в volume `r3certs` ([frontend/docker-entrypoint.sh](frontend/docker-entrypoint.sh)). Скачайте корневой CA: `GET /api/tls/root-ca` (кнопка на главной).
- **LDAP:** переменные `LDAP_*` в [docker-compose.yml](docker-compose.yml).

## Тесты и линтеры

- **Backend:** `cd backend && . .venv/bin/activate && export USE_SQLITE=true && pytest && ruff check app tests`
- **Frontend:** `cd frontend && npm run build && npm run lint` (см. [frontend/eslint.config.js](frontend/eslint.config.js))

## API (кратко)

- `POST /api/auth/login`, `GET /api/auth/me`
- `GET|PUT /api/settings` (PUT — admin+): в Redmine при самоподписанном TLS включите `redmine_insecure_ssl`, метка сложности — id списочного поля `redmine_complexity_field_id` (s…2xl); ключи ИИ **не удаляются** через API, только дополняются/обновляются
- `GET /api/settings/ai-providers`, `POST /api/settings/ai-providers/test` (admin+, проверка ключа)
- `GET /api/issues?sort=date|stale|criticality&only_stale=true`
- `POST /api/issues/{id}/suggest-split`, `POST /api/issues/{id}/subtasks`, `POST /api/issues/{id}/suggest-complexity`, `PUT /api/issues/{id}/complexity?value=`
- `GET /api/wizard/queue`, `POST /api/wizard/{id}/action`, `POST /api/wizard/{id}/ai-hint`
- `GET|PATCH /api/profile`
- `GET /api/stats/summary?from_date=&to_date=&target_user_id=`
- `GET /api/history`, `GET /api/history/all` (PM+)
- `GET /api/pm/backlog` (PM+)

Подробное ТЗ: [PROMPT.md](PROMPT.md).
