"""
SCOT — Les trois pages de l'app : Inspection en direct, Historique, Statistiques.
"""

import re
import time
from html import escape

import pandas as pd
import streamlit as st

import services as sv
import ui
from ui import CLASSES, DEFECT_CLASSES, LABELS, card, chip, class_pill, kpi

PLATE_RE = re.compile(r"^P(\d+)_(\d+)_")
UPLOAD_TYPES = ["png", "jpg", "jpeg", "bmp", "tif", "tiff"]


def plate_label(blob_name: str) -> str:
    m = PLATE_RE.match(blob_name or "")
    return f"Plaque {m.group(1)} · défaut {m.group(2)}" if m else "Envoi manuel"


def ago(ts) -> str:
    s = int((sv.now_local() - ts).total_seconds())
    if s < 60:
        return f"il y a {max(s, 0)} s"
    if s < 3600:
        return f"il y a {s // 60} min"
    if s < 86400:
        return f"il y a {s // 3600} h"
    return ts.strftime("le %d/%m à %H:%M")


# ── En-tête commun ──────────────────────────────────────────
def toolbar(title: str, subtitle: str, df: pd.DataFrame | None = None, live_toggle: bool = False) -> None:
    left, right = st.columns([1, 2.2], vertical_alignment="center")
    with left:
        st.html(f'<div class="page-title">{escape(title)}</div><div class="page-sub">{escape(subtitle)}</div>')
    with right, st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center", gap="small"):
        status = sv.model_status()
        chips = {"ok": chip("Modèle en ligne", "ok"), "pending": chip("Modèle : vérification…", "idle")}
        st.html(chips.get(status.get("status"), chip("Modèle injoignable", "bad")), width="content")
        if df is not None and not df.empty:
            last = df["Local"].max()
            fresh = (sv.now_local() - last).total_seconds() < 600
            st.html(chip(f"Dernière image {ago(last)}", "ok" if fresh else "idle"), width="content")
        if live_toggle:
            st.toggle("Temps réel", value=True, key="live", width="content")
        with st.popover("Envoyer", icon=":material/upload:"):
            upload_panel()
        user = st.session_state["user"]
        with st.popover(user["name"].split(" ")[0], icon=":material/account_circle:"):
            st.markdown(f"**{user['name']}**  \n`{user['username']}`")
            if st.button("Se déconnecter", icon=":material/logout:", width="stretch"):
                sv.log.info("Deconnexion utilisateur=%s", user["username"])
                del st.session_state["user"]
                st.rerun()
    st.write("")


def upload_panel() -> None:
    st.markdown("**Envoyer des images à analyser**")
    st.caption("Elles passent par la même chaîne que la caméra. Résultat en quelques secondes.")
    files = st.file_uploader("Images", type=UPLOAD_TYPES, accept_multiple_files=True, label_visibility="collapsed",
                             key=f"uploader_{st.session_state.get('upload_round', 0)}")
    if st.button("Analyser", type="primary", icon=":material/bolt:", disabled=not files, width="stretch"):
        with st.spinner("Envoi et analyse en cours…"):
            names, done = sv.upload_and_wait(files)
        st.session_state["upload_round"] = st.session_state.get("upload_round", 0) + 1
        if done != names:
            st.toast("Analyse plus longue que prévu : le résultat apparaîtra dans un instant.", icon="⏳")
        st.rerun()


def db_error(err) -> None:
    with card("db-error", "Base de données indisponible", "Elle se réveille probablement (jusqu'à 1 minute)."):
        st.caption(str(err)[:300])


# ── Blocs réutilisés ────────────────────────────────────────
def result_block(row, key: str) -> None:
    """Classe prédite, jauge de confiance et probabilités."""
    p = ui.pal()
    conf = float(row["Confidence"])
    color = {"ok": p["ok"], "warn": p["warn"], "bad": p["bad"]}[ui.confidence_state(conf)]
    with card(f"result-{key}", "Résultat de l'analyse", f"{row['ModelName']} · {row['InferenceMs']} ms"):
        st.html(f'<div class="big-label">Défaut détecté</div><div style="margin:6px 0 2px">'
                f'{class_pill(row["PredictedClass"], large=True)}</div>')
        ui.show(ui.gauge(conf * 100, "Indice de confiance", color, height=180), key=f"g-{key}")
        probs = ui.parse_probs(row["Probabilities"])
        if probs:
            st.html('<div class="big-label">Probabilités par classe</div>')
            ui.show(ui.proba_bars(probs), key=f"p-{key}")


def validation_block(row, key: str) -> None:
    validated = row["ValidatedClass"]
    if validated:
        same = validated == row["PredictedClass"]
        status = ui.chip("Confirmé" if same else f"Corrigé en {LABELS.get(validated, validated)}", "ok" if same else "warn")
    else:
        status = ui.chip("À valider", "idle")
    with card(f"valid-{key}", "Validation opérateur", "Confirmez ou corrigez la classe prédite", right_html=status):
        with st.form(f"form-{key}-{row['Id']}", border=False):
            current = validated or row["PredictedClass"]
            choice = st.segmented_control("Classe réelle", CLASSES, format_func=LABELS.get,
                                          default=current if current in CLASSES else None, required=True)
            comment = st.text_input("Commentaire (optionnel)", value=row["OperatorComment"] or "")
            if st.form_submit_button("Enregistrer la validation", type="primary", icon=":material/check:", width="stretch"):
                sv.save_validation(row, choice, comment)
                st.toast("Validation enregistrée", icon="✅")
                time.sleep(0.4)
                st.rerun()
        if validated:
            st.caption(f"Dernière validation : {row['ValidatedBy'] or '—'}")


def image_block(row, key: str) -> None:
    right = ui.chip(row["Local"].strftime("%d/%m/%Y %H:%M:%S"), "idle")
    with card(f"img-{key}", "Capture", plate_label(row["BlobName"]), right_html=right):
        st.image(row["BlobUrl"], width="stretch")
        st.html(f'<div class="meta">Fichier <b>{escape(row["BlobName"])}</b></div>')


# ── Page 1 : inspection en direct ───────────────────────────
def page_inspection() -> None:
    df, err = sv.get_predictions()
    toolbar("Inspection en direct", "Dernière plaque analysée et validation opérateur", df, live_toggle=True)
    interval = 5 if st.session_state.get("live", True) else None

    @st.fragment(run_every=interval)
    def live():
        df, err = sv.get_predictions()
        if err:
            db_error(err)
            return
        p = ui.pal()
        today = df[df["Local"].dt.date == sv.now_local().date()] if not df.empty else df
        defects = today[today["PredictedClass"].isin(DEFECT_CLASSES)]
        todo = df[df["ValidatedClass"].isna()]
        recent = df.head(50)

        k = st.columns(4)
        with k[0]:
            kpi("Images analysées aujourd'hui", f"{len(today)}", "image", p["accent"], f"{len(df)} au total")
        with k[1]:
            kpi("Défauts détectés aujourd'hui", f"{len(defects)}", "alert", "#F97316",
                f"{len(defects) / len(today):.0%} des images" if len(today) else "—")
        with k[2]:
            kpi("À valider", f"{len(todo)}", "clipboard", "#8B5CF6", "prédictions sans validation opérateur")
        with k[3]:
            avg = recent["Confidence"].mean() if len(recent) else 0
            ms = recent["InferenceMs"].mean() if len(recent) else 0
            kpi("Confiance moyenne", f"{avg:.0%}" if len(recent) else "—", "gauge", p["ok"],
                f"50 dernières · inférence {ms:.0f} ms" if len(recent) else "")
        st.write("")

        if df.empty:
            with card("empty", "En attente d'images", "Rien n'a encore été analysé."):
                st.markdown("Déposez une image avec **Envoyer** en haut à droite, ou démarrez le veilleur caméra.")
            return

        row = df.iloc[0]
        left, right = st.columns([1.5, 1], gap="medium")
        with left:
            image_block(row, "live")
        with right:
            result_block(row, "live")
        validation_block(row, "live")
        st.write("")

        with card("recent", "Dernières détections", "Les 6 images précédentes"):
            cols = st.columns(6)
            for col, (_, r) in zip(cols, df.iloc[1:7].iterrows()):
                with col, st.container(key=f"thumb-{r['Id']}"):
                    st.image(r["BlobUrl"], width="stretch")
                    st.html(f'{class_pill(r["PredictedClass"])}<div class="meta" style="margin-top:6px">'
                            f'{r["Local"].strftime("%d/%m %H:%M:%S")} · {r["Confidence"]:.0%}</div>')

    live()


# ── Page 2 : historique ─────────────────────────────────────
def _dialog_dismissed() -> None:
    st.session_state["dialog_dismissed"] = st.session_state.get("dialog_for")


@st.dialog("Détail de l'analyse", width="large", on_dismiss=_dialog_dismissed)
def detail_dialog(row) -> None:
    left, right = st.columns([1.3, 1], gap="medium")
    with left:
        image_block(row, "dlg")
    with right:
        result_block(row, "dlg")
    validation_block(row, "dlg")


def page_history() -> None:
    df, err = sv.get_predictions()
    toolbar("Historique", "Toutes les analyses, avec filtres et validation", df)
    if err:
        db_error(err)
        return

    with card("filters", "Filtres"):
        c1, c2, c3, c4 = st.columns([1.55, 1.6, 1, 1.1], vertical_alignment="bottom")
        status = c1.segmented_control("Statut", ["Toutes", "À valider", "Validées", "Corrigées"], default="Toutes",
                                      required=True)
        classes = c2.pills("Classe prédite", CLASSES, format_func=LABELS.get, selection_mode="multi", default=CLASSES)
        min_conf = c3.slider("Confiance minimale", 0, 100, 0, step=5, format="%d %%")
        search = c4.text_input("Rechercher", placeholder="Nom de fichier, P1_…", label_visibility="visible")
    st.write("")

    view = df[df["PredictedClass"].isin(classes or CLASSES) & (df["Confidence"] * 100 >= min_conf)]
    if status == "À valider":
        view = view[view["ValidatedClass"].isna()]
    elif status == "Validées":
        view = view[view["ValidatedClass"].notna()]
    elif status == "Corrigées":
        view = view[view["ValidatedClass"].notna() & (view["ValidatedClass"] != view["PredictedClass"])]
    if search:
        view = view[view["BlobName"].str.contains(search, case=False, regex=False)]

    table = pd.DataFrame({
        "Aperçu": view["BlobUrl"],
        "Date": view["Local"].dt.strftime("%d/%m/%Y %H:%M:%S"),
        "Plaque": view["BlobName"].map(plate_label),
        "Détection": view["PredictedClass"].map(LABELS),
        "Confiance": view["Confidence"] * 100,
        "Validation": view["ValidatedClass"].map(lambda v: LABELS.get(v, "À valider") if v else "À valider"),
        "Opérateur": view["ValidatedBy"].fillna(""),
        "Fichier": view["BlobName"],
    })
    with card("table", "Analyses", f"{len(view)} résultat(s) — cliquez sur une ligne pour voir le détail et valider"):
        event = st.dataframe(
            table, width="stretch", hide_index=True, height=560, row_height=56,
            on_select="rerun", selection_mode="single-row", key="history_table",
            column_config={
                "Aperçu": st.column_config.ImageColumn("Aperçu", width="small"),
                "Confiance": st.column_config.ProgressColumn("Confiance", format="%.0f %%", min_value=0, max_value=100),
            })

    # La fenêtre de détail reste ouverte tant que la ligne est sélectionnée, sauf si l'utilisateur l'a fermée
    rows = event.selection.rows if event and event.selection else []
    if rows:
        row = view.iloc[rows[0]]
        st.session_state["dialog_for"] = int(row["Id"])
        if st.session_state.get("dialog_dismissed") != int(row["Id"]):
            detail_dialog(row)
    else:
        st.session_state.pop("dialog_for", None)
        st.session_state.pop("dialog_dismissed", None)


# ── Page 3 : statistiques ───────────────────────────────────
def page_stats() -> None:
    df, err = sv.get_predictions()
    toolbar("Statistiques", "Volumes, confiance et performance réelle du modèle", df)
    if err:
        db_error(err)
        return
    if df.empty:
        with card("empty-stats", "Pas encore de données", "Les statistiques apparaîtront après les premières analyses."):
            pass
        return

    p = ui.pal()
    validated = df[df["ValidatedClass"].notna()]
    corrected = validated[validated["ValidatedClass"] != validated["PredictedClass"]]
    k = st.columns(4)
    with k[0]:
        kpi("Images analysées", f"{len(df)}", "image", p["accent"], f"depuis le {df['Local'].min():%d/%m/%Y}")
    with k[1]:
        kpi("Validées par un opérateur", f"{len(validated)}", "check", p["ok"],
            f"{len(validated) / len(df):.0%} des analyses")
    with k[2]:
        kpi("Taux de correction", f"{len(corrected) / len(validated):.0%}" if len(validated) else "—", "pencil",
            "#F97316", "prédictions corrigées par l'opérateur")
    with k[3]:
        kpi("Inférence moyenne", f"{df['InferenceMs'].mean():.0f} ms", "zap", "#8B5CF6", "par image, sur Azure")
    st.write("")

    c1, c2 = st.columns([1, 2], gap="medium")
    with c1, card("donut", "Répartition des détections", "Classe prédite par le modèle"):
        ui.show(ui.donut(df["PredictedClass"].value_counts()), key="donut")
    with c2, card("timeline", "Détections par jour", "Empilées par classe"):
        ui.show(ui.timeline(df), key="timeline")
    st.write("")

    c3, c4 = st.columns(2, gap="medium")
    with c3, card("hist", "Distribution de la confiance", "Rouge : peu fiable (< 50 %) · orange : à vérifier · vert : fiable (≥ 80 %)"):
        ui.show(ui.confidence_histogram(df), key="hist")
    with c4, card("perf", "Performance réelle", "Sur les images validées par un opérateur — objectif ≤ 10 % de défauts manqués"):
        real = validated[validated["ValidatedClass"].isin(DEFECT_CLASSES)]
        if real.empty:
            st.info("Validez des prédictions pour mesurer la performance réelle du modèle.", icon=":material/info:")
        else:
            missed = (real["PredictedClass"] == "sans_defaut").mean() * 100
            g, r = st.columns([1, 1.3])
            with g:
                color = p["ok"] if missed <= 10 else p["bad"]
                ui.show(ui.gauge(missed, "Défauts non détectés", color, height=200, target=10, max_value=50), key="miss")
            with r:
                rows = [{"classe": c, "n": int((validated["ValidatedClass"] == c).sum()),
                         "rappel": (validated.loc[validated["ValidatedClass"] == c, "PredictedClass"] == c).mean() * 100}
                        for c in CLASSES if (validated["ValidatedClass"] == c).any()]
                st.html('<div class="big-label">Rappel par classe (ligne : objectif 90 %)</div>')
                ui.show(ui.recall_bars(rows), key="recall")
    st.write("")

    if not validated.empty:
        with card("confusion", "Matrice de confusion", "Classe réelle (validée) × classe prédite"):
            ui.show(ui.confusion_heatmap(validated), key="cm")
