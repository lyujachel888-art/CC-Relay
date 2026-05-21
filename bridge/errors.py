# bridge/errors.py
"""Custom exceptions for bridge — keeps callers from catching bare Exception."""


class WrapperConflict(Exception):
    """Same wrapper id already registered and still online."""


class WrapperOffline(Exception):
    """Target wrapper exists but is currently offline (no recent heartbeat)."""


class WrapperUnknown(Exception):
    """No wrapper with this id has ever been registered."""


class BadToken(Exception):
    """Heartbeat/deregister called with wrong or missing token."""
