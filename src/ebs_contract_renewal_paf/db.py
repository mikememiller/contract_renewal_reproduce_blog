"""
================================================================================
 Syntax Corporation © 2026 — All Rights Reserved
--------------------------------------------------------------------------------
 Project : EBS Contract Renewal PAF — BPA Renewal Automation Agent
 Module  : db.py — python-oracledb THICK-mode connection manager
 Version : 1.0.0      Build : 2026.06.04      Date : 2026-06-04
--------------------------------------------------------------------------------
 The EBS Vision database enforces Oracle Native Network Encryption (NNE).
 python-oracledb THIN mode fails with DPY-3001, so we MUST run THICK mode with
 the Instant Client (see memory: ebs-db-connection).

 This module:
   * initialises thick mode exactly once (idempotent),
   * builds a SID-based DSN (EBSDB is a SID, not a service name),
   * exposes a small query helper that uses BIND VARIABLES only — never string
     interpolation — so the data layer is injection-safe by construction.
================================================================================
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from .config import Settings

_thick_initialised = False


def _ensure_thick(instant_client_dir: str) -> None:
    """Initialise python-oracledb thick mode once per process (idempotent)."""
    global _thick_initialised
    if _thick_initialised:
        return
    import oracledb

    lib_dir = str(Path(instant_client_dir).expanduser())
    if not Path(lib_dir).is_dir():
        raise RuntimeError(
            f"Oracle Instant Client not found at '{lib_dir}'. "
            "Thick mode is required for the NNE-protected EBS DB. "
            "Set EBS_INSTANT_CLIENT_DIR or install the client."
        )
    try:
        oracledb.init_oracle_client(lib_dir=lib_dir)
    except Exception as exc:  # already-initialised raises; tolerate that
        if "already" not in str(exc).lower():
            raise
    _thick_initialised = True


class EBSConnection:
    """Thin context-managed wrapper around an oracledb connection.

    Usage:
        with EBSConnection(settings) as db:
            rows = db.query("SELECT 1 FROM dual")
    """

    def __init__(self, settings: Settings, *, interactive: bool = True):
        self.settings = settings
        self._interactive = interactive
        self._conn = None

    def __enter__(self) -> "EBSConnection":
        import oracledb

        _ensure_thick(self.settings.instant_client_dir)
        dsn = oracledb.makedsn(
            self.settings.host, self.settings.port, sid=self.settings.sid
        )
        self._conn = oracledb.connect(
            user=self.settings.user,
            password=self.settings.get_password(interactive=self._interactive),
            dsn=dsn,
        )
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    @property
    def connection(self):
        if self._conn is None:
            raise RuntimeError("EBSConnection used outside its context manager.")
        return self._conn

    def query(
        self, sql: str, params: Sequence[Any] | dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Run a SELECT and return rows as dicts (lower-cased column names).

        `params` MUST carry every dynamic value as bind variables.
        """
        with self._cursor() as cur:
            cur.execute(sql, params or {})
            cols = [d[0].lower() for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def query_one(
        self, sql: str, params: Sequence[Any] | dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    @contextmanager
    def _cursor(self) -> Iterator[Any]:
        cur = self.connection.cursor()
        try:
            yield cur
        finally:
            cur.close()


def dialtone(settings: Settings, *, interactive: bool = True) -> bool:
    """Lightweight connectivity probe — returns True if SELECT 1 succeeds."""
    try:
        with EBSConnection(settings, interactive=interactive) as db:
            return db.query_one("SELECT 1 AS ok FROM dual") == {"ok": 1}
    except Exception:
        return False
