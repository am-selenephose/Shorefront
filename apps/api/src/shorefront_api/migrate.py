from __future__ import annotations

import json

from .storage import OperationsStore


def main() -> None:
    store = OperationsStore()
    status = store.migrate_schema()
    print(json.dumps(status, sort_keys=True))


if __name__ == "__main__":
    main()
