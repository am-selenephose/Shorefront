"""Establish test isolation before collection imports the application singleton."""
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

_test_data = TemporaryDirectory(prefix='shorefront-pytest-')
_original_settings = {key: value for key, value in os.environ.items()
                      if key == 'DATABASE_URL' or key.startswith(('SHOREFRONT_', 'PORTFLOW_'))}
for _key in _original_settings:
    os.environ.pop(_key, None)
os.environ.update({
    'DATABASE_URL': f"sqlite:///{Path(_test_data.name) / 'test.db'}",
    'SHOREFRONT_DATA_DIR': _test_data.name,
    'SHOREFRONT_SCHEMA_MODE': 'migrate',
    'SHOREFRONT_PUBLIC_MODE': '0',
    'SHOREFRONT_STATIC_DIR': '',
    'SHOREFRONT_APPROVERS_JSON': '[]',
    'SHOREFRONT_INTEGRATIONS_JSON': '[]',
    'SHOREFRONT_AIS_URL': '',
    'SHOREFRONT_WEATHER_URL': '',
    'SHOREFRONT_BERTH_PLAN_URL': '',
})


def pytest_unconfigure(config):
    application = sys.modules.get('shorefront_api.main')
    if application is not None:
        application.store.engine.dispose()
    _test_data.cleanup()
    for key in list(os.environ):
        if key == 'DATABASE_URL' or key.startswith(('SHOREFRONT_', 'PORTFLOW_')):
            os.environ.pop(key, None)
    os.environ.update(_original_settings)
