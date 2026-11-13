"""
SCOT — Comptes utilisateurs de l'app web.

Les comptes sont stockés dans le paramètre d'application SCOT_USERS (App Settings
Azure), au format JSON :
    {"arthur.col": {"name": "Arthur Col", "hash": "pbkdf2_sha256$300000$<sel>$<empreinte>"}}

Aucun mot de passe n'est stocké en clair : seulement une empreinte PBKDF2-SHA256
salée. Gestion des comptes : scripts/gerer_comptes.py.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets

ALGO = "pbkdf2_sha256"
ITERATIONS = 300_000


def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    b64 = lambda b: base64.b64encode(b).decode("ascii")  # noqa: E731
    return f"{ALGO}${iterations}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_b64, digest_b64 = stored.split("$")
        if algo != ALGO:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                     base64.b64decode(salt_b64), int(iterations))
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except (ValueError, TypeError):
        return False


def load_users() -> dict:
    """Comptes définis dans SCOT_USERS ; dictionnaire vide si le paramètre est absent."""
    raw = os.environ.get("SCOT_USERS", "").strip()
    if not raw:
        return {}
    try:
        users = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return users if isinstance(users, dict) else {}


def authenticate(username: str, password: str) -> dict | None:
    """Renvoie {"username", "name"} si l'identifiant et le mot de passe sont corrects."""
    username = (username or "").strip().lower()
    user = load_users().get(username)
    if not user:
        # Même coût de calcul qu'un vrai compte, pour ne pas révéler les identifiants existants
        verify_password(password or "", hash_password("leurre", ITERATIONS))
        return None
    if verify_password(password or "", user.get("hash", "")):
        return {"username": username, "name": user.get("name") or username}
    return None


def running_on_azure() -> bool:
    return bool(os.environ.get("WEBSITE_SITE_NAME"))
