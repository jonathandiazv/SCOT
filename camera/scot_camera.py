"""
SCOT — Veilleur du dossier caméra.

Surveille en continu le dossier où le SDK caméra dépose les images traitées
(une image par défaut détecté, rangées dans des sous-dossiers par date) et envoie
chaque image jamais envoyée dans le conteneur Blob `blob-scot`. L'envoi déclenche
ensuite toute la chaîne Azure : Event Grid → Function (ONNX) → SQL → app web.

Nommage attendu (fixé par le SDK) : P<plaque>_<défaut>_<YYMMDDHHMMSS>.<ext>
  ex. P1_1_261113143005.png = plaque 1, 1er défaut découpé, 13/11/2026 14:30:05
      P1_2_261113143005.png = plaque 1, 2e défaut de la même plaque

Une image n'est jamais envoyée deux fois :
  1. un journal local SQLite garde les noms déjà envoyés ;
  2. l'envoi est en « création seulement » : si le blob existe déjà, Azure refuse
     et l'image est simplement notée comme envoyée.

Usage :
  python camera\\scot_camera.py                     # utilise camera\\config.json
  python camera\\scot_camera.py --config autre.json
  python camera\\scot_camera.py --une-fois          # un seul balayage puis arrêt (tests)
"""

import argparse
import json
import logging
import logging.handlers
import queue
import re
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from azure.core.exceptions import HttpResponseError, ResourceExistsError
from azure.storage.blob import ContainerClient, ContentSettings
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

HERE = Path(__file__).resolve().parent
NAME_RE = re.compile(r"^P(?P<plaque>\d+)_(?P<defaut>\d+)_(?P<horodatage>\d{12})\.(?P<ext>png|jpe?g|bmp|tiff?)$",
                     re.IGNORECASE)
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
CONTENT_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".bmp": "image/bmp", ".tif": "image/tiff", ".tiff": "image/tiff"}

DEFAULTS = {
    "dossier_images": "",            # dossier racine des images TRAITÉES (pas les brutes)
    "url_sas_conteneur": "",         # https://projetscot.blob.core.windows.net/blob-scot?<jeton SAS>
    "url_sante_function": "https://fn-scot-app-fnascbfubbeududg.francecentral-01.azurewebsites.net/api/health",
    "balayage_secondes": 30,         # balayage complet de sécurité
    "stabilite_secondes": 1.0,       # le fichier ne doit plus changer pendant ce délai
    "reveil_function_secondes": 300, # garde la Function éveillée (0 = désactivé)
    "journal": "camera_envoyees.db",
    "fichier_log": "logs/scot_camera.log",
}

log = logging.getLogger("scot_camera")


# ── Configuration et logs ───────────────────────────────────
def load_config(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"Configuration introuvable : {path}\nCopiez camera\\config.example.json en config.json et remplissez-le.")
    cfg = {**DEFAULTS, **json.loads(path.read_text(encoding="utf-8"))}
    if not cfg["dossier_images"] or not Path(cfg["dossier_images"]).is_dir():
        sys.exit(f"dossier_images invalide : {cfg['dossier_images']!r}")
    if not cfg["url_sas_conteneur"].startswith("https://"):
        sys.exit("url_sas_conteneur manquante (voir camera\\creer_jeton_camera.ps1).")
    for key in ("journal", "fichier_log"):
        p = Path(cfg[key])
        cfg[key] = str(p if p.is_absolute() else HERE / p)
    return cfg


def setup_logging(log_file: str) -> None:
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    file_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    log.addHandler(file_handler)
    log.addHandler(console)
    log.setLevel(logging.INFO)
    logging.getLogger("azure").setLevel(logging.WARNING)


# ── Journal des images déjà envoyées ────────────────────────
class Journal:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.execute("""CREATE TABLE IF NOT EXISTS envoyees (
            nom TEXT PRIMARY KEY, chemin TEXT, taille INTEGER, envoyee_le TEXT, statut TEXT)""")
        self.db.commit()

    def deja_envoyee(self, nom: str) -> bool:
        with self.lock:
            return self.db.execute("SELECT 1 FROM envoyees WHERE nom = ?", (nom,)).fetchone() is not None

    def noter(self, nom: str, chemin: Path, taille: int, statut: str) -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO envoyees VALUES (?, ?, ?, ?, ?)",
                            (nom, str(chemin), taille, datetime.now(timezone.utc).isoformat(), statut))
            self.db.commit()


# ── Envoi ───────────────────────────────────────────────────
def deja_presente(e: Exception) -> bool:
    """L'image existe déjà dans le conteneur.

    Avec un jeton « création seule », Azure ne répond pas 409 (existe déjà) mais
    403 « not authorized to perform blob overwrites » : les deux veulent dire
    « déjà envoyée ».
    """
    if isinstance(e, ResourceExistsError):
        return True
    return (isinstance(e, HttpResponseError) and e.status_code == 403
            and "overwrite" in str(e).lower())


class Veilleur:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.root = Path(cfg["dossier_images"])
        self.journal = Journal(cfg["journal"])
        self.container = ContainerClient.from_container_url(cfg["url_sas_conteneur"], max_single_put_size=256 * 1024 * 1024)
        self.todo: "queue.Queue[Path]" = queue.Queue()
        self.en_attente: set[str] = set()
        self.ignorees: set[str] = set()
        self.lock = threading.Lock()

    def proposer(self, path: Path) -> None:
        """Ajoute un fichier à la file s'il s'agit d'une image jamais envoyée."""
        if path.suffix.lower() not in IMAGE_EXTS or not path.is_file():
            return  # .tmp, dossiers, autres fichiers : ignorés sans bruit
        nom = path.name
        if not NAME_RE.match(nom):
            if nom not in self.ignorees:
                self.ignorees.add(nom)
                log.warning("Nom hors format, image ignorée : %s", path)
            return
        with self.lock:
            if nom in self.en_attente or self.journal.deja_envoyee(nom):
                return
            self.en_attente.add(nom)
        self.todo.put(path)

    def balayer(self) -> int:
        """Parcourt tout le dossier (sous-dossiers compris) dans l'ordre des noms."""
        avant = self.todo.qsize()
        for p in sorted(self.root.rglob("*"), key=lambda x: x.name):
            self.proposer(p)
        return self.todo.qsize() - avant

    def attendre_fichier_complet(self, path: Path, delai_max: float = 60) -> bool:
        """Attend que la taille ne change plus et que le fichier soit lisible."""
        stabilite = self.cfg["stabilite_secondes"]
        fin = time.time() + delai_max
        derniere = -1
        while time.time() < fin:
            try:
                taille = path.stat().st_size
                if taille > 0 and taille == derniere:
                    with open(path, "rb"):
                        return True
                derniere = taille
            except (FileNotFoundError, PermissionError):
                pass
            time.sleep(stabilite)
        return False

    def envoyer(self, path: Path) -> None:
        nom = path.name
        try:
            if not self.attendre_fichier_complet(path):
                log.warning("Fichier jamais stabilisé ou illisible, réessai au prochain balayage : %s", path)
                return
            data = path.read_bytes()
            delai = 2
            while True:
                try:
                    self.container.upload_blob(
                        nom, data, overwrite=False,
                        content_settings=ContentSettings(content_type=CONTENT_TYPES.get(path.suffix.lower())))
                    self.journal.noter(nom, path, len(data), "envoyee")
                    log.info("Envoyée : %s (%d Ko)", nom, len(data) // 1024)
                    return
                except Exception as e:  # noqa: BLE001
                    if deja_presente(e):
                        self.journal.noter(nom, path, len(data), "deja_presente")
                        log.info("Déjà présente dans Azure, non renvoyée : %s", nom)
                        return
                    if isinstance(e, HttpResponseError) and e.status_code == 403:
                        log.error("Accès refusé pour %s : jeton SAS expiré ou révoqué ? "
                                  "(camera\\creer_jeton_camera.ps1) — nouvel essai dans %d s", nom, delai)
                    else:  # réseau coupé, Azure indisponible…
                        log.error("Échec d'envoi de %s : %s — nouvel essai dans %d s", nom, str(e).splitlines()[0], delai)
                    time.sleep(delai)
                    delai = min(delai * 2, 300)
        finally:
            with self.lock:
                self.en_attente.discard(nom)

    # ── Boucles ─────────────────────────────────────────────
    def boucle_envoi(self) -> None:
        while True:
            path = self.todo.get()
            self.envoyer(path)

    def boucle_balayage(self) -> None:
        while True:
            time.sleep(self.cfg["balayage_secondes"])
            n = self.balayer()
            if n:
                log.info("Balayage : %d image(s) rattrapée(s)", n)

    def boucle_reveil(self) -> None:
        intervalle = self.cfg["reveil_function_secondes"]
        while intervalle > 0:
            try:
                requests.get(self.cfg["url_sante_function"], timeout=60)
            except Exception as e:  # noqa: BLE001
                log.warning("Function injoignable : %s", e)
            time.sleep(intervalle)


class Evenements(FileSystemEventHandler):
    def __init__(self, veilleur: Veilleur):
        self.v = veilleur

    def on_created(self, event):
        if not event.is_directory:
            self.v.proposer(Path(event.src_path))

    def on_moved(self, event):  # cas « écrit en .tmp puis renommé »
        if not event.is_directory:
            self.v.proposer(Path(event.dest_path))

    def on_modified(self, event):
        if not event.is_directory:
            self.v.proposer(Path(event.src_path))


def main() -> None:
    ap = argparse.ArgumentParser(description="Veilleur du dossier caméra SCOT")
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--une-fois", action="store_true", help="un balayage, envoi, puis arrêt")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    setup_logging(cfg["fichier_log"])
    v = Veilleur(cfg)
    log.info("Démarrage — dossier surveillé : %s", v.root)

    n = v.balayer()
    log.info("Rattrapage au démarrage : %d image(s) à envoyer", n)

    if args.une_fois:
        while not v.todo.empty():
            v.envoyer(v.todo.get())
        log.info("Terminé (--une-fois).")
        return

    threading.Thread(target=v.boucle_envoi, daemon=True, name="envoi").start()
    threading.Thread(target=v.boucle_balayage, daemon=True, name="balayage").start()
    threading.Thread(target=v.boucle_reveil, daemon=True, name="reveil").start()

    observer = Observer()
    observer.schedule(Evenements(v), str(v.root), recursive=True)
    observer.start()
    log.info("En écoute (Ctrl+C pour arrêter).")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Arrêt demandé.")
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
