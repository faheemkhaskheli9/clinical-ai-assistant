"""Small shared guards against the most obvious accidental-PII mistakes.

These are *not* a PII detector — real de-identification happens upstream,
before any identifier reaches a schema in this package. They exist so the
same cheap check is applied identically everywhere a pseudonymous identifier
is accepted (robustness rule 10: harden sibling schemas the same way).
"""

from __future__ import annotations


def reject_email_shaped_identifier(value: str) -> str:
    """Return ``value`` unchanged, or raise if it looks like an email address.

    Catches the common slip of passing a raw email as a patient identifier.
    """
    if "@" in value:
        raise ValueError(
            "identifier must be pseudonymous (never a real name, email, or SSN); "
            "got a value containing '@'"
        )
    return value
