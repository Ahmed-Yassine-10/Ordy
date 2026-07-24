"""ordy-sandbox — the isolated browser runner (doc 08 §5).

One run = one container = one order attempt. Containers are never reused across tenants,
have no database credentials, and can only reach the approved target domain.
"""

__version__ = "0.1.0"
