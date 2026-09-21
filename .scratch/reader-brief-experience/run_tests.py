"""Run regression tests in a disposable local database with external tracing disabled."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from sqlalchemy.engine import make_url

from zhigenews.settings import get_settings

database_name = "zhigenews_brief_test_" + uuid4().hex[:12]
mysql = ["docker", "exec", "-i", "zhigenews-mysql-1", "sh", "-c",
         'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot']
subprocess.run(mysql, input=f"CREATE DATABASE {database_name}; GRANT ALL ON {database_name}.* TO 'zhigenews'@'%';",
               text=True, capture_output=True, check=True)
settings = get_settings()
os.environ["DATABASE_URL"] = make_url(settings.database_url).set(database=database_name).render_as_string(hide_password=False)
os.environ["HARNESS_TEST_MYSQL_URL"] = os.environ["DATABASE_URL"]
os.environ["LANGSMITH_TRACING"] = "false"
try:
    with tempfile.TemporaryDirectory(prefix="zgb-", dir=Path.cwd().anchor) as test_tmp:
        os.environ["DATA_DIR"] = str(Path(test_tmp) / "data")
        get_settings.cache_clear()
        from zhigenews.db import Base, engine
        Base.metadata.create_all(engine())
        from zhigenews.harness import mysql_persistence
        with mysql_persistence(os.environ["DATABASE_URL"], setup=True):
            pass
        import pytest
        result = pytest.main(["--basetemp=" + str(Path(test_tmp) / "pytest"), *sys.argv[1:]])
        engine().dispose()
        raise SystemExit(result)
finally:
    subprocess.run(mysql, input=f"DROP DATABASE {database_name};", text=True, capture_output=True, check=True)
