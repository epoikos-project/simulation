"""
db_utils.py

Utility for optimistic concurrency updates on TinyDB tables.
"""
from tinydb import TinyDB, Query


class ConcurrentWriteError(Exception):
    """Raised when an optimistic concurrency conflict occurs during a safe_update."""
    pass


def safe_update(table: TinyDB.table_class, cond, data: dict) -> None:
    """
    Perform an optimistic concurrency update on a TinyDB table row.

    - Loads the existing row matching 'cond', reads its 'version' (default 0).
    - Increments version by 1 and merges it into 'data'.
    - Updates the row only if its version still matches the old one.
    - Raises ConcurrentWriteError if the update did not succeed due to version mismatch.
    """
    # fetch existing row
    row = table.get(cond)
    old_version = row.get("version", 0) if row else 0
    new_version = old_version + 1
    payload = dict(data)
    payload["version"] = new_version

    # only update if version has not changed
    table.update(payload, cond & (Query().version == old_version))

    # verify successful update
    updated = table.get(cond)
    if updated.get("version") != new_version:
        raise ConcurrentWriteError(
            f"Version conflict (expected {old_version} -> {new_version}) on cond={cond}."
        )