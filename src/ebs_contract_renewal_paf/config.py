"""
================================================================================
 Syntax Corporation © 2026 — All Rights Reserved
--------------------------------------------------------------------------------
 Project : EBS Contract Renewal PAF — BPA Renewal Automation Agent
 Module  : config.py — runtime settings resolution
 Version : 1.0.0      Build : 2026.06.04      Date : 2026-06-04
--------------------------------------------------------------------------------
 Resolves connection / runtime settings with a clear precedence:

     explicit kwargs  >  JSON config file  >  environment variables  >  defaults

 The password is NEVER hard-coded. It is sourced (in order) from an explicit
 value, the EBS_PASSWORD env var, the JSON file (with a warning), or — as a last
 resort — an interactive getpass prompt at connect time.
================================================================================
"""

from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Built-in defaults — the EBS Vision instance (see memory: ebs-db-connection).
_DEFAULTS: dict[str, Any] = {
    "host": "172.16.3.44",
    "port": 1521,
    "sid": "EBSDB",
    "user": "APPS",
    "org_id": 204,
    "instant_client_dir": "~/lib/oracle/instantclient",
    "backend": "mock",              # safe default; the CLI/tests opt into "live"
    "extractor": "deterministic",   # deterministic | llm | auto
    "llm_model": "claude-opus-4-8",
}


@dataclass
class Settings:
    """Resolved runtime settings for one agent run."""

    host: str
    port: int
    sid: str
    user: str
    org_id: int
    instant_client_dir: str
    backend: str
    extractor: str
    llm_model: str
    # Password handled separately so it never lands in a dataclass repr/log.
    _password: str | None = field(default=None, repr=False)

    # ------------------------------------------------------------------
    @classmethod
    def resolve(
        cls,
        config_path: str | Path | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> "Settings":
        """Build Settings using precedence: overrides > JSON > env > defaults."""
        values: dict[str, Any] = dict(_DEFAULTS)

        # env layer
        env_map = {
            "host": "EBS_HOST",
            "port": "EBS_PORT",
            "sid": "EBS_SID",
            "user": "EBS_USER",
            "org_id": "EBS_ORG_ID",
            "instant_client_dir": "EBS_INSTANT_CLIENT_DIR",
            "backend": "EBS_BACKEND",
            "extractor": "EBS_EXTRACTOR",
            "llm_model": "EBS_LLM_MODEL",
        }
        for key, env_name in env_map.items():
            if (env_val := os.environ.get(env_name)) is not None:
                values[key] = env_val

        # JSON file layer (documented precedence: flag > JSON > env > default).
        password_from_json: str | None = None
        if config_path:
            data = json.loads(Path(config_path).expanduser().read_text())
            for key in list(values) + ["password"]:
                if key in data and data[key] is not None:
                    if key == "password":
                        password_from_json = str(data[key])
                    else:
                        values[key] = data[key]
            if password_from_json:
                warnings.warn(
                    "Password read from JSON config; prefer EBS_PASSWORD env "
                    "var or the interactive prompt.",
                    stacklevel=2,
                )

        # explicit overrides win
        if overrides:
            for key, val in overrides.items():
                if val is not None and key in values:
                    values[key] = val

        # normalise types
        values["port"] = int(values["port"])
        values["org_id"] = int(values["org_id"])

        # password precedence: override > env > JSON
        password = None
        if overrides:
            password = overrides.get("password")
        password = password or os.environ.get("EBS_PASSWORD") or password_from_json

        return cls(_password=password, **{k: values[k] for k in env_map})

    # ------------------------------------------------------------------
    def get_password(self, *, interactive: bool = True) -> str:
        """Return the password, prompting via getpass only if needed."""
        if self._password:
            return self._password
        if not interactive:
            raise RuntimeError(
                "No EBS password available (set EBS_PASSWORD or pass --password)."
            )
        import getpass

        pw = getpass.getpass(f"Password for {self.user}@{self.sid}: ")
        if not pw:
            raise RuntimeError("Empty password.")
        self._password = pw
        return pw
