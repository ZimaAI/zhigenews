"""Run this feature's checks in a separate local MySQL database and storage."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from sqlalchemy.engine import make_url

from zhigenews.settings import get_settings

database_name = "zhigenews_source_test_" + uuid4().hex[:12]
subprocess.run(
    ["docker", "exec", "-i", "zhigenews-mysql-1", "sh", "-c",
     'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot'],
    input=f"CREATE DATABASE {database_name}; "
          f"GRANT ALL ON {database_name}.* TO 'zhigenews'@'%';",
    text=True, capture_output=True, check=True,
)
settings = get_settings()
os.environ["DATABASE_URL"] = make_url(settings.database_url).set(database=database_name).render_as_string(hide_password=False)
os.environ["ZHIGENEWS_DISPOSABLE_SOURCE_DB"] = database_name
os.environ["DATA_DIR"] = str(Path(__file__).parent.resolve() / "test-data")
os.environ["LANGSMITH_TRACING"] = "false"
get_settings.cache_clear()

from zhigenews.db import Base, engine

Base.metadata.create_all(engine())
import pytest

try:
    with tempfile.TemporaryDirectory(prefix="zgs-", dir=Path.cwd().anchor) as test_tmp:
        raise SystemExit(pytest.main(["--basetemp=" + test_tmp, *sys.argv[1:]]))
finally:
    engine().dispose()
    subprocess.run(
        ["docker", "exec", "-i", "zhigenews-mysql-1", "sh", "-c",
         'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot'],
        input=f"DROP DATABASE {database_name};", text=True, capture_output=True, check=True,
    )
