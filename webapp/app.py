"""
SCOT — Panneau de contrôle de l'inspection (Azure App Service).

L'inférence est faite par l'Azure Function (fn-scot-app) : cette app ne charge aucun
modèle. Elle lit les prédictions dans Azure SQL et les images dans le Blob, permet
d'envoyer des images et de corriger les prédictions (correction experte).

Organisation :
  app.py       connexion + navigation
  views.py     les trois pages (Inspection, Historique, Statistiques)
  ui.py        thème clair/sombre, composants et graphiques
  services.py  données SQL/Blob, état de la Function, logs
Lancer en local : powershell -ExecutionPolicy Bypass -File webapp\\run_local.ps1
"""

import time
from pathlib import Path

import streamlit as st

import scot_auth
import services as sv
import ui
import views

HERE = Path(__file__).resolve().parent

st.set_page_config(page_title="SCOT · Inspection", page_icon=str(HERE / "static" / "logo.svg"), layout="wide")
ui.inject_css()
st.logo(str(HERE / "static" / "logo.svg"), size="large")

MAX_ATTEMPTS = 5
LOCK_SECONDS = 60


def login_page() -> None:
    sv.prewarm()  # réveille la Function et la base pendant la saisie du mot de passe
    users = scot_auth.load_users()
    _, col, _ = st.columns([1, 1.05, 1])
    with col:
        st.write("")
        st.write("")
        with st.container(key="card-login"):
            st.html('<div class="login-brand"><div class="t">SCOT</div>'
                    '<div class="s">Système de Contrôle Optique Transparent</div></div>')
            if not users:
                st.error("Aucun compte n'est configuré sur ce serveur. Voir scripts/gerer_comptes.py.")
                return
            locked_until = st.session_state.get("locked_until", 0)
            if time.time() < locked_until:
                st.error(f"Trop de tentatives. Réessayez dans {int(locked_until - time.time()) + 1} s.")
                return
            with st.form("login", border=False):
                username = st.text_input("Identifiant", placeholder="prenom.nom")
                password = st.text_input("Mot de passe", type="password")
                submitted = st.form_submit_button("Se connecter", type="primary", width="stretch")
            if submitted:
                user = scot_auth.authenticate(username, password)
                if user:
                    st.session_state["user"] = user
                    st.session_state["failed"] = 0
                    sv.log.info("Connexion reussie utilisateur=%s", user["username"])
                    st.rerun()
                failed = st.session_state.get("failed", 0) + 1
                st.session_state["failed"] = failed
                sv.log.warning("Connexion refusee identifiant=%s tentative=%d", username.strip().lower()[:60], failed)
                if failed >= MAX_ATTEMPTS:
                    st.session_state["locked_until"] = time.time() + LOCK_SECONDS
                    st.session_state["failed"] = 0
                    st.error(f"Trop de tentatives. Réessayez dans {LOCK_SECONDS} s.")
                else:
                    st.error("Identifiant ou mot de passe incorrect.")
            st.caption("Pas de compte ? Demandez-le à Jonathan Diaz Vreys.")


def main() -> None:
    if "user" not in st.session_state:
        if not scot_auth.load_users() and not scot_auth.running_on_azure():
            # En local, sans comptes configurés : accès direct pour développer
            st.session_state["user"] = {"username": "local", "name": "Développeur local", "role": "admin"}
        else:
            st.navigation([st.Page(login_page, title="Connexion", icon=":material/lock:")], position="hidden").run()
            return

    pages = [
        st.Page(views.page_inspection, title="Inspection", icon=":material/center_focus_strong:",
                url_path="inspection", default=True),
        st.Page(views.page_history, title="Historique", icon=":material/history:", url_path="historique"),
        st.Page(views.page_stats, title="Statistiques", icon=":material/monitoring:", url_path="statistiques"),
    ]
    if st.session_state["user"].get("role") == "admin":
        pages.append(st.Page(views.page_admin, title="Administration", icon=":material/admin_panel_settings:",
                             url_path="administration"))
    st.navigation(pages, position="top").run()


main()
