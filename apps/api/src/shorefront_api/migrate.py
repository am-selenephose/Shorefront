from __future__ import annotations

import json

from .storage import OperationsStore
from .config import setting


def main() -> None:
    runtime_mode = setting('RUNTIME_MODE', 'operational').strip().lower()
    if runtime_mode not in {'operational', 'training'}:
        raise RuntimeError('SHOREFRONT_RUNTIME_MODE must be operational or training')
    if runtime_mode == 'operational':
        from .product_api import create_product_app
        owner = setting('INSTALLATION_ID', '')
        if not owner:
            raise RuntimeError('Set SHOREFRONT_INSTALLATION_ID before operational migration')
        store = create_product_app().state.product_store
        try:
            store.initialize()
            print(json.dumps({'runtime_mode':'operational','installation_id':owner,'schema_version':1,'migrated':True}, sort_keys=True))
        finally:
            store.engine.dispose()
        return
    store = OperationsStore()
    status = store.migrate_schema()
    print(json.dumps(status, sort_keys=True))


if __name__ == "__main__":
    main()
