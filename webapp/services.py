"""
SCOT — Services de l'app web : logs, données SQL/Blob, état de la Function.

Aucune mise en forme ici : l'affichage est dans ui.py et views.py.
"""

import logging
import os
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

import scot_data

TZ = ZoneInfo("Europe/Paris")
FUNCTION_HEALTH_URL = os.environ.get(
    "FUNCTION_HEALTH_URL",
    "https://fn-scot-app-fnascbfubbeududg.francecentral-01.azurewebsites.net/api/health",
)


# ── Logs (Application Insights sur Azure) ───────────────────
@st.cache_resource
def get_logger() -> logging.Logger:
    logger = logging.getLogger("scot")
    logger.setLevel(logging.INFO)
    if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor
            configure_azure_monitor(logger_name="scot")
        except Exception as e:  # noqa: BLE001 — la télémétrie ne doit jamais bloquer l'app
            logging.getLogger(__name__).warning("Application Insights non initialisé : %s", e)
    return logger


log = get_logger()


# ── Prédictions ─────────────────────────────────────────────
@st.cache_data(ttl=5, show_spinner=False)
def load_predictions() -> pd.DataFrame:
    df = scot_data.fetch_predictions(limit=500)
    if not df.empty:
        df["Local"] = df["CreatedAt"].dt.tz_convert(TZ)
    return df


def get_predictions():
    """(DataFrame, erreur) : ne lève jamais d'exception, pour que la page s'affiche quand même."""
    try:
        return load_predictions(), None
    except Exception as e:  # noqa: BLE001
        log.error("Base de données indisponible : %s", e)
        return pd.DataFrame(columns=[*scot_data.COLUMNS, "Local"]), e


def save_validation(row, validated_class: str, comment: str) -> None:
    user = st.session_state["user"]
    scot_data.save_validation(row["Id"], validated_class, user["name"], comment)
    log.info("Validation prediction=%s predite=%s reelle=%s operateur=%s",
             row["Id"], row["PredictedClass"], validated_class, user["username"])
    load_predictions.clear()


def upload_and_wait(files, timeout: int = 45) -> tuple[set, set]:
    """Envoie les images dans blob-scot puis attend leur analyse par la Function."""
    names = {scot_data.upload_image(f.name, f.getvalue(), f.type) for f in files}
    log.info("Envoi de %d image(s) par %s : %s", len(names), st.session_state["user"]["username"],
             ", ".join(sorted(names)))
    done: set = set()
    deadline = time.time() + timeout  # Event Grid + Function : ~3 à 15 s (plus au démarrage à froid)
    while time.time() < deadline:
        time.sleep(2)
        done = set(scot_data.fetch_predictions(limit=50)["BlobName"]) & names
        if done == names:
            break
    load_predictions.clear()
    return names, done


# ── État de la Function d'inférence ─────────────────────────
class HealthMonitor:
    """Interroge /api/health en arrière-plan toutes les 2 min ; l'affichage n'attend jamais."""

    def __init__(self, interval: int = 120):
        self.status = {"status": "pending"}
        self.interval = interval
        threading.Thread(target=self._loop, daemon=True, name="scot-health").start()

    def _loop(self):
        while True:
            try:
                self.status = requests.get(FUNCTION_HEALTH_URL, timeout=60).json()
            except Exception as e:  # noqa: BLE001
                self.status = {"status": "error", "detail": str(e)}
            time.sleep(self.interval)


@st.cache_resource
def health_monitor() -> HealthMonitor:
    return HealthMonitor()


def model_status() -> dict:
    return health_monitor().status


def prewarm() -> None:
    """Réveille la Function et la base SQL en arrière-plan (au plus une fois par minute)."""
    health_monitor()
    if time.time() - st.session_state.get("prewarmed_at", 0) < 60:
        return
    st.session_state["prewarmed_at"] = time.time()

    def warm_sql():
        try:
            scot_data.fetch_predictions(limit=1)
        except Exception as e:  # noqa: BLE001
            log.warning("Prechauffage SQL echoue : %s", e)

    threading.Thread(target=warm_sql, daemon=True, name="scot-prewarm").start()


def now_local() -> datetime:
    return datetime.now(TZ)
