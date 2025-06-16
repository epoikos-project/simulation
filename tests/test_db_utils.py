
import pytest
from tinydb import TinyDB, Query
from tinydb.storages import MemoryStorage

from models.db_utils import safe_update, ConcurrentWriteError


def test_safe_update_increments_version_and_updates_row():
    db = TinyDB(storage=MemoryStorage)
    table = db.table('test')
    table.insert({'id': 'x', 'value': 1, 'version': 0})
    cond = Query().id == 'x'

    safe_update(table, cond, {'value': 42})
    row = table.get(cond)
    assert row['value'] == 42
    assert row['version'] == 1


def test_safe_update_conflict_raises_and_does_not_override():
    db = TinyDB(storage=MemoryStorage)
    table = db.table('test')
    table.insert({'id': 'x', 'value': 1, 'version': 0})
    cond = Query().id == 'x'

    # simulate update failure (e.g. concurrent write) by no-oping table.update
    orig_update = table.update
    table.update = lambda *args, **kwargs: None
    try:
        with pytest.raises(ConcurrentWriteError):
            safe_update(table, cond, {'value': 99})
    finally:
        table.update = orig_update

    # ensure the row remains unchanged by the failed safe_update
    row = table.get(cond)
    assert row['value'] == 1
    assert row['version'] == 0