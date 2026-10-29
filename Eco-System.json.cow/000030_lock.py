#!/usr/bin/env python3
"""Lock-Handling für eco-update und eco-gc-retention."""

import fcntl
from pathlib import Path


LOCKFILE = "/run/lock/eco-update.lock"
HOOK_ENV_VAR = "ECO_UPDATE_HOLDING_LOCK"


def acquire_lock():
    """Erwirbt den Lock. Rückgabe: file object oder None."""
    try:
        Path("/run/lock").mkdir(exist_ok=True)
        fd = open(LOCKFILE, "w")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BlockingIOError:
        return None
    except Exception:
        return None


def release_lock(fd):
    """Gibt den Lock frei. Kein unlink — flock arbeitet auf Inodes."""
    if fd is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()
        except Exception:
            pass


def hook_is_holding_lock() -> bool:
    """True, wenn wir als Post-Update-Hook laufen (Parent hält Lock)."""
    import os
    return os.environ.get(HOOK_ENV_VAR) == "1"
