"""Disposable MySQL + synthetic sources for manual browser acceptance."""
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy.engine import make_url
from zhigenews.settings import get_settings

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = Path(__file__).parent / "runtime"
RUNTIME.mkdir(exist_ok=True)
database = "zhigenews_source_ui_" + uuid4().hex[:12]
assert re.fullmatch(r"zhigenews_source_ui_[0-9a-f]{12}", database)


def sql(command):
    result = subprocess.run(
        ["docker", "exec", "-i", "zhigenews-mysql-1", "sh", "-c",
         'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot'],
        input=command, text=True, capture_output=True,
    )
    if result.returncode:
        raise RuntimeError("Fixture database command failed")


sql(f"CREATE DATABASE {database}; GRANT ALL ON {database}.* TO 'zhigenews'@'%';")
os.environ["DATABASE_URL"] = make_url(get_settings().database_url).set(database=database).render_as_string(hide_password=False)
os.environ["DATA_DIR"] = str(RUNTIME / database)
os.environ["ALLOWED_ORIGINS"] = '["http://127.0.0.1:5186"]'
os.environ["LANGSMITH_TRACING"] = "false"
get_settings.cache_clear()

from sqlalchemy import select
from fastapi.testclient import TestClient
from zhigenews.db import Resource, SourceDeletionJob, User, engine, transaction
from zhigenews.security import password_hash

try:
    migration = subprocess.run([str(ROOT / 'backend/.venv/Scripts/python.exe'), '-m', 'alembic', '-c', str(ROOT / 'backend/alembic.ini'), 'upgrade', 'head'], cwd=ROOT, capture_output=True)
    assert migration.returncode == 0, "Fixture migration failed"
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from zhigenews.db import Base
    with engine().connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    print('Fresh MySQL migration and metadata comparison passed', flush=True)
    with transaction() as session:
        session.add(User(id='synthetic-source-admin', name='模拟验收管理员', role='admin', email='source-ui@example.test', password_hash=password_hash('Synthetic-browser-2026')))
    from zhigenews.gateway import app
    with TestClient(app, headers={'X-Zhige-Request':'1', 'Origin':'http://127.0.0.1:5186'}) as client:
        assert client.post('/api/v1/admin/auth/login', json={'email':'source-ui@example.test','password':'Synthetic-browser-2026'}).status_code == 200
        ids = []
        for n in range(16):
            response = client.post('/api/v1/admin/sources', json={'name':f'模拟来源 {n:02d}', 'kind':'rss','sourceId':'','url':f'https://fixture.invalid/{n}','interval':600})
            assert response.status_code == 201
            ident = response.json()['id']; ids.append(ident)
            if n >= 10:
                with transaction() as session:
                    row = session.get(Resource, ident)
                    row.private = {'state':{'failure_count':3}}
                folder = get_settings().data_dir / 'rss' / ident
                folder.mkdir(parents=True)
                (folder / 'synthetic.json').write_text('{}')
    # Artificial delay exposes intermediate UI states; cleanup itself is real.
    from zhigenews import sources
    from zhigenews.source_deletions import execute_job
    original = sources.shutil.rmtree
    def delayed(path, *args, **kwargs):
        time.sleep(3)
        if path.name == ids[10]:
            raise PermissionError('Synthetic cleanup failure')
        return original(path, *args, **kwargs)
    sources.shutil.rmtree = delayed
    busy_lock = sources.source_lock(ids[11]); busy_lock.acquire()
    stop = threading.Event()
    def worker():
        while not stop.wait(.3):
            with transaction() as session:
                job = session.scalar(select(SourceDeletionJob).where(SourceDeletionJob.active_slot == 'sources'))
                ident = job.id if job else None
            if ident:
                execute_job(ident)
    threading.Thread(target=worker, daemon=True).start()
    print('Synthetic browser fixture ready on 18006', flush=True)
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=18006, log_level='warning')
finally:
    if 'stop' in locals():
        stop.set()
    if 'busy_lock' in locals():
        busy_lock.release()
    engine().dispose()
    assert re.fullmatch(r"zhigenews_source_ui_[0-9a-f]{12}", database)
    sql(f"DROP DATABASE {database};")
