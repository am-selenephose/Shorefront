"""The app used by tests must never inherit a developer's database or feeds."""
import os
from pathlib import Path
import tempfile

import shorefront_api.main as api


def test_test_application_is_bound_to_a_dedicated_temporary_database():
    url = api.store.engine.url
    assert url.drivername == 'sqlite'
    database = Path(url.database)
    assert database.parent.parent == Path(tempfile.gettempdir())
    assert database.parent.name.startswith('shorefront-pytest-')
    assert database.name == 'test.db'
    assert os.environ['SHOREFRONT_SCHEMA_MODE'] == 'migrate'
    assert os.environ['SHOREFRONT_PUBLIC_MODE'] == '0'
    assert os.environ['SHOREFRONT_STATIC_DIR'] == ''
    for suffix in ('AIS_URL', 'WEATHER_URL', 'BERTH_PLAN_URL'):
        assert os.environ['SHOREFRONT_' + suffix] == ''
