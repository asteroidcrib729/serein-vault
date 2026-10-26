"""Errors safe to display to the user without exposing keys or plaintext."""


class VaultError(Exception):
    """An expected operation failure."""


class AuthenticationError(VaultError):
    """The password is incorrect or encrypted data has been damaged."""


class FormatError(VaultError):
    """The input does not use a supported format."""


class VaultBusyError(VaultError):
    """Another instance owns this vault."""


class OperationCancelled(VaultError):
    """The user cancelled before an output was published."""
