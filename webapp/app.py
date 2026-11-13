"""
SCOT — Tableau de bord d'inspection (version cloud).

L'inférence est faite par l'Azure Function (fn-scot-app) : cette app ne charge
aucun modèle. Elle lit les prédictions dans Azure SQL et les images dans le Blob,
permet d'envoyer des images et de corriger les prédictions (correction experte).

Lancer en local :  python -m streamlit run webapp/app.py   (après `az login`)
"""

import json
import logging
import os
import threading
import time

import altair as alt
import pandas as pd
import requests
import streamlit as st

import scot_auth
import scot_data


@st.cache_resource
def get_logger() -> logging.Logger:
    """Envoie les logs « scot » vers Application Insights si la connexion est configurée (sur Azure)."""
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

CLASSES = ["tache", "rayure", "inclusion", "sans_defaut"]
DEFECT_CLASSES = ["tache", "rayure", "inclusion"]
COLORS = {"tache": "#ff6b35", "rayure": "#00d4ff", "inclusion": "#7b61ff", "sans_defaut": "#10b981"}
FUNCTION_HEALTH_URL = os.environ.get(
    "FUNCTION_HEALTH_URL",
    "https://fn-scot-app-fnascbfubbeududg.francecentral-01.azurewebsites.net/api/health",
)

st.set_page_config(page_title="SCOT - Système de Contrôle Optique Transparent",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #1F2937; }
    section[data-testid="stSidebar"] { background-color: #F3F4F6; border-right: 1px solid #E5E7EB; }
    h1, h2, h3 { color: #111827 !important; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-weight: 700; }
    .status-card { padding: 24px; border-radius: 8px; background-color: #F9FAFB; border: 1px solid #E5E7EB; margin-bottom: 20px; }
    .metric-label { color: #6B7280; font-size: 0.85rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
    .metric-value { color: #111827; font-size: 2rem; font-weight: 800; }
    .border-success { border-left: 6px solid #10B981; }
    .border-warning { border-left: 6px solid #F59E0B; }
    .border-danger { border-left: 6px solid #EF4444; }
    div.stButton > button:first-child { background-color: #2563EB; color: white; border-radius: 6px; border: none; padding: 0.5rem 1rem; font-weight: 600; width: 100%; }
    div.stButton > button:hover { background-color: #1D4ED8; color: white; border: none; }
    .logo-container { font-size: 2.5rem; font-weight: 900; color: #2563EB; letter-spacing: -2px; margin-bottom: 0; padding-bottom: 0; }
    .logo-sub { font-size: 0.8rem; color: #6B7280; margin-top: -10px; font-weight: 500; line-height: 1.2; }
    </style>
""", unsafe_allow_html=True)


# ── Données ─────────────────────────────────────────────────
@st.cache_data(ttl=5, show_spinner=False)
def load_predictions() -> pd.DataFrame:
    return scot_data.fetch_predictions(limit=500)


class HealthMonitor:
    """Interroge /api/health de la Function en arrière-plan, toutes les 2 minutes.

    L'affichage lit le dernier résultat connu sans jamais attendre : quand la Function
    est en veille, son réveil (rechargement du modèle de 45 Mo) prend 5 à 20 s.
    """

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


def get_predictions():
    try:
        return load_predictions(), None
    except Exception as e:  # noqa: BLE001
        return pd.DataFrame(columns=scot_data.COLUMNS), e


# ── Composants ──────────────────────────────────────────────
def proba_chart(probabilities_json: str):
    try:
        probs = json.loads(probabilities_json or "{}")
    except json.JSONDecodeError:
        probs = {}
    if not probs:
        return
    df = pd.DataFrame({"Classe": list(probs), "Probabilité": [v * 100 for v in probs.values()]})
    chart = alt.Chart(df).mark_bar().encode(
        x=alt.X("Probabilité:Q", scale=alt.Scale(domain=[0, 100]), title="Probabilité (%)"),
        y=alt.Y("Classe:N", sort=CLASSES, title=None),
        color=alt.Color("Classe:N", scale=alt.Scale(domain=list(COLORS), range=list(COLORS.values())), legend=None),
        tooltip=["Classe", alt.Tooltip("Probabilité:Q", format=".1f")],
    ).properties(height=180)
    st.altair_chart(chart, use_container_width=True)


def result_card(row):
    conf = row["Confidence"]
    border = "border-success" if conf > 0.8 else "border-warning" if conf > 0.5 else "border-danger"
    cls = row["PredictedClass"]
    validated = row["ValidatedClass"]
    extra = ""
    if validated:
        verdict = "✔ confirmé" if validated == cls else f"✎ corrigé en <b>{validated.upper()}</b>"
        extra = f'<div style="margin-top:10px;color:#374151;">Opérateur : {verdict}</div>'
    st.markdown(f"""
        <div class="status-card {border}">
            <div class="metric-label">Type de Défaut Détecté</div>
            <div class="metric-value" style="color:{COLORS.get(cls, '#111827')};">{cls.upper()}</div>
            <hr style="border:0.5px solid #E5E7EB;margin:15px 0;">
            <div class="metric-label">Indice de Confiance</div>
            <div class="metric-value">{conf:.1%}</div>
            {extra}
        </div>""", unsafe_allow_html=True)


def validation_form(row, key: str):
    """Correction experte : l'opérateur confirme ou corrige la classe prédite."""
    operator = st.session_state["user"]["name"]
    with st.form(f"validate_{key}_{row['Id']}", border=True):
        st.markdown("**Validation opérateur**")
        current = row["ValidatedClass"] or row["PredictedClass"]
        choice = st.radio("Classe réelle", CLASSES, index=CLASSES.index(current) if current in CLASSES else 0,
                          horizontal=True)
        comment = st.text_input("Commentaire (optionnel)", value=row["OperatorComment"] or "")
        st.caption(f"Enregistrée au nom de : {operator}")
        if st.form_submit_button("Enregistrer la validation"):
            scot_data.save_validation(row["Id"], choice, operator, comment)
            log.info("Validation prediction=%s predite=%s reelle=%s operateur=%s",
                     row["Id"], row["PredictedClass"], choice, operator)
            load_predictions.clear()
            st.success("Validation enregistrée.")
            time.sleep(0.6)
            st.rerun()


# ── Onglets ─────────────────────────────────────────────────
def tab_inspection(df: pd.DataFrame):
    if df.empty:
        st.info("En attente d'images : déposez-en une avec « Envoyer des images » dans la barre latérale.")
        return
    row = df.iloc[0]
    col_img, col_res = st.columns([3, 2])
    with col_img:
        st.subheader("Capture Courante")
        st.image(row["BlobUrl"], caption=f"Fichier : {row['BlobName']}", use_container_width=True)
    with col_res:
        st.subheader("Résultat de l'analyse")
        result_card(row)
        proba_chart(row["Probabilities"])
        st.caption(f"Analysé le {row['CreatedAt'].tz_convert('Europe/Paris'):%d/%m/%Y %H:%M:%S} · "
                   f"{row['ModelName']} · {row['InferenceMs']} ms")
        validation_form(row, "live")


def tab_history(df: pd.DataFrame):
    st.subheader("Journal des Analyses")
    if df.empty:
        st.info("Aucune analyse enregistrée.")
        return
    c1, c2, c3 = st.columns(3)
    classes = c1.multiselect("Classe prédite", CLASSES, default=CLASSES)
    status = c2.selectbox("Statut", ["Toutes", "À valider", "Validées", "Corrigées"])
    min_conf = c3.slider("Confiance minimale", 0, 100, 0, step=5)

    view = df[df["PredictedClass"].isin(classes) & (df["Confidence"] * 100 >= min_conf)]
    if status == "À valider":
        view = view[view["ValidatedClass"].isna()]
    elif status == "Validées":
        view = view[view["ValidatedClass"].notna()]
    elif status == "Corrigées":
        view = view[view["ValidatedClass"].notna() & (view["ValidatedClass"] != view["PredictedClass"])]

    table = pd.DataFrame({
        "Id": view["Id"],
        "Date": view["CreatedAt"].dt.tz_convert("Europe/Paris").dt.strftime("%d/%m %H:%M:%S"),
        "Fichier": view["BlobName"],
        "Détection": view["PredictedClass"].str.upper(),
        "Confiance": view["Confidence"] * 100,
        "Validation": view["ValidatedClass"].fillna("—").str.upper(),
        "Opérateur": view["ValidatedBy"].fillna(""),
    })
    event = st.dataframe(
        table, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row",
        column_config={"Confiance": st.column_config.ProgressColumn("Confiance", format="%.1f %%",
                                                                    min_value=0, max_value=100)},
    )
    st.caption(f"{len(view)} analyse(s). Sélectionnez une ligne pour voir l'image et la valider.")

    selected = event.selection.rows if event and event.selection else []
    if selected:
        row = view.iloc[selected[0]]
        c_img, c_res = st.columns([3, 2])
        c_img.image(row["BlobUrl"], caption=row["BlobName"], use_container_width=True)
        with c_res:
            result_card(row)
            proba_chart(row["Probabilities"])
            validation_form(row, "hist")


def tab_stats(df: pd.DataFrame):
    st.subheader("Statistiques")
    if df.empty:
        st.info("Les statistiques seront disponibles après les premières détections.")
        return
    validated = df[df["ValidatedClass"].notna()]
    corrected = validated[validated["ValidatedClass"] != validated["PredictedClass"]]

    m = st.columns(4)
    m[0].metric("Images analysées", len(df))
    m[1].metric("Validées par un opérateur", len(validated))
    m[2].metric("Taux de correction", f"{len(corrected) / len(validated):.0%}" if len(validated) else "—")
    m[3].metric("Inférence moyenne", f"{df['InferenceMs'].mean():.0f} ms")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Répartition des détections**")
        counts = df["PredictedClass"].value_counts().reindex(CLASSES, fill_value=0).reset_index()
        counts.columns = ["Classe", "Nombre"]
        st.altair_chart(alt.Chart(counts).mark_bar().encode(
            x=alt.X("Classe:N", sort=CLASSES, title=None), y="Nombre:Q",
            color=alt.Color("Classe:N", scale=alt.Scale(domain=list(COLORS), range=list(COLORS.values())),
                            legend=None)).properties(height=260), use_container_width=True)
    with c2:
        st.markdown("**Distribution de la confiance**")
        st.altair_chart(alt.Chart(df.assign(Conf=df["Confidence"] * 100)).mark_bar(color="#2563EB").encode(
            x=alt.X("Conf:Q", bin=alt.Bin(step=10), title="Confiance (%)"), y=alt.Y("count()", title="Nombre"),
        ).properties(height=260), use_container_width=True)

    st.markdown("**Performance réelle (sur les images validées par un opérateur)**")
    if validated.empty:
        st.info("Validez des prédictions pour mesurer la performance réelle du modèle.")
        return
    st.caption("Objectif SCOT : au plus 10 % de défauts non détectés, soit un rappel ≥ 90 % sur les classes défaut.")
    rows = []
    for c in CLASSES:
        truth = validated[validated["ValidatedClass"] == c]
        if len(truth):
            rows.append({"Classe réelle": c, "Images": len(truth),
                         "Rappel": (truth["PredictedClass"] == c).mean() * 100})
    real_defects = validated[validated["ValidatedClass"].isin(DEFECT_CLASSES)]
    if len(real_defects):
        missed = (real_defects["PredictedClass"] == "sans_defaut").mean()
        st.metric("Défauts réels non détectés (prédits « sans_defaut »)", f"{missed:.0%}",
                  delta="objectif ≤ 10 %", delta_color="off")
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                 column_config={"Rappel": st.column_config.ProgressColumn("Rappel", format="%.0f %%",
                                                                          min_value=0, max_value=100)})
    st.markdown("**Matrice de confusion (prédit × réel)**")
    st.dataframe(pd.crosstab(validated["ValidatedClass"], validated["PredictedClass"],
                             rownames=["Réel"], colnames=["Prédit"]), use_container_width=True)


# ── Barre latérale ──────────────────────────────────────────
def sidebar():
    with st.sidebar:
        st.markdown('<div class="logo-container">SCOT</div>', unsafe_allow_html=True)
        st.markdown('<div class="logo-sub">Système de Contrôle Optique Transparent</div>', unsafe_allow_html=True)
        st.divider()

        st.subheader("Opérateur")
        user = st.session_state["user"]
        st.markdown(f"Connecté : **{user['name']}**")
        if st.button("Se déconnecter", use_container_width=True):
            log.info("Deconnexion utilisateur=%s", user["username"])
            del st.session_state["user"]
            st.rerun()

        st.subheader("Modèle d'IA")
        status = model_status()
        if status.get("status") == "ok":
            st.success(f"En ligne : {status.get('model')}")
            st.caption("Inférence : Azure Function (ONNX, CPU)")
        elif status.get("status") == "pending":
            st.info("Vérification de la Function d'inférence…")
            st.caption("Si elle est en veille, la première analyse prend 10 à 20 s de plus.")
        else:
            st.error("Function d'inférence injoignable")
            st.caption(str(status.get("detail", ""))[:200])

        st.divider()
        st.subheader("Envoyer des images")
        files = st.file_uploader("Images à analyser", type=["png", "jpg", "jpeg", "bmp", "tif", "tiff"],
                                 accept_multiple_files=True, label_visibility="collapsed",
                                 key=f"uploader_{st.session_state.get('upload_round', 0)}")
        if files and st.button("Analyser", use_container_width=True):
            with st.spinner("Envoi vers Azure…"):
                names = {scot_data.upload_image(f.name, f.getvalue(), f.type) for f in files}
            log.info("Envoi de %d image(s) par %s : %s", len(names), st.session_state["user"]["username"],
                     ", ".join(sorted(names)))
            st.session_state["upload_round"] = st.session_state.get("upload_round", 0) + 1
            with st.spinner("Analyse par l'IA en cours…"):
                deadline = time.time() + 45   # Event Grid + Function : ~5 à 15 s (plus au démarrage à froid)
                while time.time() < deadline:
                    time.sleep(3)
                    done = set(scot_data.fetch_predictions(limit=50)["BlobName"]) & names
                    if done == names:
                        break
            load_predictions.clear()
            if done != names:
                st.toast("Analyse plus longue que prévu : cliquez sur « Actualiser maintenant » dans un instant.")
            st.rerun()

        st.divider()
        st.subheader("Surveillance")
        auto = st.toggle("Mode Temps Réel (Auto-Scan)", value=False)
        interval = st.slider("Intervalle (secondes)", 5, 60, 10) if auto else None
        if st.button("Actualiser maintenant", use_container_width=True):
            load_predictions.clear()
            st.rerun()
    return interval


# ── Connexion ───────────────────────────────────────────────
MAX_ATTEMPTS = 5
LOCK_SECONDS = 60


def login_page() -> bool:
    """Affiche la page de connexion. Renvoie True si un utilisateur est connecté."""
    if "user" in st.session_state:
        return True

    prewarm()  # pendant la saisie du mot de passe
    users = scot_auth.load_users()
    if not users and not scot_auth.running_on_azure():
        # En local, sans comptes configurés : accès direct pour développer
        st.session_state["user"] = {"username": "local", "name": "Développeur (local)"}
        return True

    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.markdown('<div class="logo-container">SCOT</div>', unsafe_allow_html=True)
        st.markdown('<div class="logo-sub">Système de Contrôle Optique Transparent</div>', unsafe_allow_html=True)
        st.write("")
        if not users:
            st.error("Aucun compte n'est configuré sur ce serveur. Voir scripts/gerer_comptes.py.")
            return False

        locked_until = st.session_state.get("locked_until", 0)
        if time.time() < locked_until:
            st.error(f"Trop de tentatives. Réessayez dans {int(locked_until - time.time()) + 1} s.")
            return False

        with st.form("login"):
            st.subheader("Connexion")
            username = st.text_input("Identifiant", placeholder="prenom.nom")
            password = st.text_input("Mot de passe", type="password")
            submitted = st.form_submit_button("Se connecter")
        if submitted:
            user = scot_auth.authenticate(username, password)
            if user:
                st.session_state["user"] = user
                st.session_state["failed"] = 0
                log.info("Connexion reussie utilisateur=%s", user["username"])
                st.rerun()
            failed = st.session_state.get("failed", 0) + 1
            st.session_state["failed"] = failed
            log.warning("Connexion refusee identifiant=%s tentative=%d", username.strip().lower()[:60], failed)
            if failed >= MAX_ATTEMPTS:
                st.session_state["locked_until"] = time.time() + LOCK_SECONDS
                st.session_state["failed"] = 0
                st.error(f"Trop de tentatives. Réessayez dans {LOCK_SECONDS} s.")
            else:
                st.error("Identifiant ou mot de passe incorrect.")
        st.caption("Pas de compte ? Demandez-le à Jonathan Diaz Vreys.")
    return False


def main():
    if not login_page():
        return
    interval = sidebar()
    st.title("Tableau de Bord - Inspection")
    tab_i, tab_h, tab_s = st.tabs(["Inspection Directe", "Historique des Détections", "Statistiques"])

    with tab_i:
        @st.fragment(run_every=interval)
        def live():
            df, err = get_predictions()
            if err:
                log.error("Base de données indisponible : %s", err)
                st.error(f"Base de données indisponible (elle se réveille peut-être, ~1 min) : {err}")
                return
            tab_inspection(df)
        live()

    df, err = get_predictions()
    if err:
        return
    with tab_h:
        tab_history(df)
    with tab_s:
        tab_stats(df)


main()
