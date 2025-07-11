# Minecraft Server Monitor

A system to monitor player counts on multiple Minecraft servers and generate graphs.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment variables in `.env`:
```bash
DATABASE_URL=postgresql://username:password@localhost/minecraft_monitor
# Or for SQLite: DATABASE_URL=sqlite:///./minecraft_monitor.db
```

3. Initialize the database:
```bash
cd src
alembic init alembic
alembic revision --autogenerate -m "Initial migration"
alembic upgrade head
```

4. Set up the cron job for the scraper:
```bash
crontab -e
# Add this line:
*/15 * * * * cd /path/to/project && /usr/bin/python3 src/scraper.py >> /var/log/minecraft_scraper.log 2>&1
```

5. Run the API server:
```bash
cd src
python api.py
# Or with uvicorn:
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

## API Endpoints

- `GET /` - API root
- `GET /servers` - List all monitored servers
- `GET /graph/{server_id}?period={days}` - Generate player count graph
- `GET /stats/{server_id}?period={days}` - Get server statistics

## Directory Structure

```
minecraft-server-monitor/
├── .env
├── requirements.txt
├── servers.json
├── README.md
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── script.py.mako
└── src/
    ├── __init__.py
    ├── scraper.py
    ├── api.py
    └── models/
        ├── __init__.py
        ├── database.py
        └── models.py
```