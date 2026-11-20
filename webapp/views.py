"""
SCOT — Les pages de l'app (Inspection, Historique, Statistiques, Administration) et la barre latérale.
"""

import re
import time
from html import escape

import pandas as pd
import streamlit as st

import services as sv
import ui
from ui import CLASSES, DEFECT_CLASSES, LABELS, card, chip, class_pill, fmt_pct, kpi

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


# ── Barre latérale (sous le menu) ───────────────────────────
@st.fragment(run_every=15)
def _side_status() -> None:
    status = sv.model_status().get("status")
    color, text = {"ok": ("#4CB97A", "Modèle en ligne"),
                   "pending": ("#9AA7BA", "Vérification du modèle…")}.get(status, ("#E06C6C", "Modèle injoignable"))
    df, _ = sv.get_predictions()
    last = f"Dernière image {escape(ago(df['Local'].max()))}" if df is not None and not df.empty else "Aucune image"
    st.html(f'<div class="side-status"><span class="side-dot" style="background:{color}"></span>'
            f'<b>{text}</b><br>{last}</div>')


def sidebar_panel() -> None:
    """État du modèle, temps réel, envoi d'images et compte : sous le menu de navigation."""
    st.html('<div class="side-sep"></div>')
    _side_status()
    st.toggle("Temps réel", value=True, key="live", help="Rafraîchit la page Inspection toutes les 5 secondes.")
    with st.popover("Envoyer des images", icon=":material/upload:", width="stretch"):
        upload_panel()
    user = st.session_state["user"]
    role = "Administrateur" if user.get("role") == "admin" else "Opérateur"
    with st.popover(user["name"], icon=":material/account_circle:", width="stretch"):
        st.caption(f"{user['username']} · {role}")
        if st.button("Se déconnecter", icon=":material/logout:", width="stretch"):
            sv.log.info("Deconnexion utilisateur=%s", user["username"])
            del st.session_state["user"]
            st.rerun()


def page_header(title: str, subtitle: str) -> None:
    st.html(f'<div class="page-title">{escape(title)}</div><div class="page-sub">{escape(subtitle)}</div>')
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
    with card("db-error", "Base de données indisponible", "Elle se réveille probablement (jusqu'à 1 minute).",
              state="bad"):
        st.caption(str(err)[:300])


# ── Blocs réutilisés ────────────────────────────────────────
def validation_form(row, key: str) -> None:
    validated = row["ValidatedClass"]
    with st.form(f"form-{key}-{row['Id']}", border=False):
        current = validated or row["PredictedClass"]
        choice = st.segmented_control("Classe réelle", CLASSES, format_func=LABELS.get,
                                      default=current if current in CLASSES else None, required=True)
        comment = st.text_input("Commentaire (optionnel)", value=row["OperatorComment"] or "")
        if st.form_submit_button("Valider", type="primary", icon=":material/check:", width="stretch"):
            sv.save_validation(row, choice, comment)
            st.toast("Validation enregistrée", icon="✅")
            time.sleep(0.4)
            st.rerun()


def result_card(row, key: str) -> None:
    """Résultat et validation dans une seule carte, dont la bordure gauche indique le statut.

    Confiance ≥ seuil : validée automatiquement, correction possible via « Corriger la classe ».
    Confiance < seuil : bandeau orange et formulaire de validation directement visible.
    """
    thr = sv.threshold()
    status = sv.status_of(row, thr)
    state = ui.STATUS_STATE[status]
    conf = float(row["Confidence"])
    validated = row["ValidatedClass"]
    by = row["ValidatedBy"] or "un opérateur"
    text = {
        "a_valider": f"Validation requise · confiance {fmt_pct(conf)} < {thr:.0%}",
        "auto": f"Validée automatiquement · confiance ≥ {thr:.0%}",
        "confirmee": f"Confirmée par {by}",
        "corrigee": f"Corrigée en {LABELS.get(validated, validated)} par {by}",
    }[status]
    with card(f"result-{key}", "Résultat", f"{row['ModelName']} · {row['InferenceMs']} ms", state=state):
        st.html(f'<div class="big-label">Classe détectée</div><div style="margin-top:2px">'
                f'{class_pill(row["PredictedClass"], large=True)}'
                f'<span class="conf" style="color:{ui.pal()[state]}">{fmt_pct(conf)}</span></div>'
                f'<div style="margin-top:12px">{ui.proba_html(ui.parse_probs(row["Probabilities"]))}</div>'
                + ui.banner(text, state))
        if status == "a_valider":
            validation_form(row, key)
        else:
            with st.expander("Corriger la classe" if status == "auto" else "Modifier la validation",
                             icon=":material/edit:"):
                validation_form(row, key)


def image_block(row, key: str) -> None:
    right = chip(row["Local"].strftime("%d/%m/%Y %H:%M:%S"), "idle")
    with card(f"img-{key}", plate_label(row["BlobName"]), right_html=right):
        st.image(row["BlobUrl"], width="stretch")
        st.html(f'<div class="meta">Fichier <b>{escape(row["BlobName"])}</b></div>')


# ── Page 1 : inspection en direct ───────────────────────────
def page_inspection() -> None:
    page_header("Inspection en direct", "Dernière plaque analysée et validation opérateur")
    interval = 5 if st.session_state.get("live", True) else None

    @st.fragment(run_every=interval)
    def live():
        df, err = sv.get_predictions()
        if err:
            db_error(err)
            return
        df = sv.with_status(df)
        today = df[df["Local"].dt.date == sv.now_local().date()] if not df.empty else df
        defects = today[today["PredictedClass"].isin(DEFECT_CLASSES)]
        todo = df[df["Statut"] == "a_valider"]
        recent = df.head(50)

        k = st.columns(4)
        with k[0]:
            kpi("Images aujourd'hui", f"{len(today)}", f"{len(df)} au total")
        with k[1]:
            kpi("Défauts détectés", f"{len(defects)}",
                f"{len(defects) / len(today):.0%} des images du jour" if len(today) else "aujourd'hui")
        with k[2]:
            kpi("À valider", f"{len(todo)}", f"confiance < {sv.threshold():.0%}", state="warn" if len(todo) else None)
        with k[3]:
            avg = recent["Confidence"].mean() if len(recent) else 0
            ms = recent["InferenceMs"].mean() if len(recent) else 0
            kpi("Confiance moyenne", f"{avg:.0%}" if len(recent) else "—",
                f"50 dernières · inférence {ms:.0f} ms" if len(recent) else "")
        st.write("")

        if df.empty:
            with card("empty", "En attente d'images", "Rien n'a encore été analysé."):
                st.markdown("Envoyez une image avec **Envoyer des images** dans le menu à gauche, "
                            "ou démarrez le veilleur caméra.")
            return

        row = df.iloc[0]
        left, right = st.columns([1.3, 1], gap="medium")
        with left:
            image_block(row, "live")
        with right:
            result_card(row, "live")
        st.write("")

        with card("recent", "Dernières détections", "Les 6 images précédentes · trait de couleur : statut de validation"):
            cols = st.columns(6)
            for col, (_, r) in zip(cols, df.iloc[1:7].iterrows()):
                with col, st.container(key=f"thumb-{r['Id']}--{ui.STATUS_STATE[r['Statut']]}"):
                    st.image(r["BlobUrl"], width="stretch")
                    st.html(f'{class_pill(r["PredictedClass"])}<div class="meta" style="margin-top:2px">'
                            f'{r["Local"].strftime("%d/%m %H:%M:%S")} · {r["Confidence"]:.0%}</div>')

    live()


# ── Page 2 : historique ─────────────────────────────────────
def _dialog_dismissed() -> None:
    st.session_state["dialog_dismissed"] = st.session_state.get("dialog_for")


@st.dialog("Détail de l'analyse", width="large", on_dismiss=_dialog_dismissed)
def detail_dialog(row) -> None:
    left, right = st.columns([1.2, 1], gap="medium")
    with left:
        image_block(row, "dlg")
    with right:
        result_card(row, "dlg")


def page_history() -> None:
    df, err = sv.get_predictions()
    page_header("Historique", f"Toutes les analyses · seuil de validation automatique : {sv.threshold():.0%}")
    if err:
        db_error(err)
        return
    df = sv.with_status(df)

    with card("filters"):
        c1, c2, c3, c4 = st.columns([1.5, 1.4, 0.9, 1.1], vertical_alignment="bottom", gap="medium")
        status = c1.selectbox("Statut", ["toutes", *sv.STATUS_LABELS],
                              format_func=lambda s: "Tous les statuts" if s == "toutes" else sv.STATUS_LABELS[s])
        classes = c2.multiselect("Classe prédite", CLASSES, format_func=LABELS.get, placeholder="Toutes les classes")
        min_conf = c3.slider("Confiance min.", 0, 100, 0, step=5, format="%d %%")
        search = c4.text_input("Rechercher", placeholder="Fichier, P1_…")
    st.write("")

    view = df[df["PredictedClass"].isin(classes or CLASSES) & (df["Confidence"] * 100 >= min_conf)]
    if status != "toutes":
        view = view[view["Statut"] == status]
    if search:
        view = view[view["BlobName"].str.contains(search, case=False, regex=False)]

    table = pd.DataFrame({
        "Aperçu": view["BlobUrl"],
        "Date": view["Local"].dt.strftime("%d/%m/%Y %H:%M:%S"),
        "Plaque": view["BlobName"].map(plate_label),
        "Détection": view["PredictedClass"].map(LABELS),
        "Confiance": view["Confidence"] * 100,
        "Statut": view.apply(lambda r: f"Corrigée → {LABELS.get(r['ValidatedClass'], r['ValidatedClass'])}"
                             if r["Statut"] == "corrigee" else sv.STATUS_LABELS[r["Statut"]], axis=1),
        "Opérateur": view["ValidatedBy"].fillna(""),
        "Fichier": view["BlobName"],
    })
    # Colonne Statut écrite dans la couleur d'état (vert / orange / gris-bleu)
    p = ui.pal()
    state_colors = [p[ui.STATUS_STATE[s]] for s in view["Statut"]]
    styled = table.reset_index(drop=True).style.apply(
        lambda col: [f"color:{c};font-weight:600" for c in state_colors], subset=["Statut"])
    with card("table", "Analyses", f"{len(view)} résultat(s) — cliquez sur une ligne pour voir le détail et valider"):
        event = st.dataframe(
            styled, width="stretch", hide_index=True, height=560, row_height=56,
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
    page_header("Statistiques", "Volumes, confiance et performance réelle du modèle")
    if err:
        db_error(err)
        return
    if df.empty:
        with card("empty-stats", "Pas encore de données", "Les statistiques apparaîtront après les premières analyses."):
            pass
        return

    df = sv.with_status(df)
    thr = sv.threshold()
    validated = df[df["ValidatedClass"].notna()]
    corrected = validated[validated["ValidatedClass"] != validated["PredictedClass"]]
    auto = df[df["Statut"] == "auto"]
    k = st.columns(4)
    with k[0]:
        kpi("Images analysées", f"{len(df)}", f"depuis le {df['Local'].min():%d/%m/%Y}")
    with k[1]:
        kpi("Validées automatiquement", f"{len(auto) / len(df):.0%}",
            f"{len(auto)} image(s) avec confiance ≥ {thr:.0%}")
    with k[2]:
        kpi("Validées par un opérateur", f"{len(validated)}",
            f"dont {len(corrected)} corrigée(s) · {len(corrected) / len(validated):.0%}" if len(validated) else "aucune")
    with k[3]:
        kpi("Inférence moyenne", f"{df['InferenceMs'].mean():.0f} ms", "par image, sur Azure")
    st.write("")

    c1, c2 = st.columns([1, 2], gap="medium")
    with c1, card("classes", "Répartition des détections", "Classe prédite par le modèle"):
        ui.show(ui.class_bars(df["PredictedClass"].value_counts()), key="classes")
    with c2, card("timeline", "Détections par jour", "Empilées par classe"):
        ui.show(ui.timeline(df), key="timeline")
    st.write("")

    c3, c4 = st.columns(2, gap="medium")
    with c3, card("hist", "Distribution de la confiance", "En bleu : au-dessus du seuil de validation automatique"):
        ui.show(ui.confidence_histogram(df, threshold=thr), key="hist")
    with c4, card("perf", "Performance réelle", "Sur les images validées par un opérateur — objectif ≤ 10 % de défauts manqués"):
        real = validated[validated["ValidatedClass"].isin(DEFECT_CLASSES)]
        if real.empty:
            st.info("Validez des prédictions pour mesurer la performance réelle du modèle.", icon=":material/info:")
        else:
            missed = (real["PredictedClass"] == "sans_defaut").mean() * 100
            g, r = st.columns([1, 1.5], gap="medium")
            with g:
                state = "ok" if missed <= 10 else "bad"
                st.html(f'<div class="big-label">Défauts non détectés</div>'
                        f'<div class="cls lg" style="color:{ui.pal()[state]};margin-top:4px">{fmt_pct(missed / 100)}</div>'
                        f'<div class="meta" style="margin-top:4px">objectif ≤ 10 % · {len(real)} défaut(s) validé(s)</div>'
                        + ui.banner("Objectif atteint" if state == "ok" else "Objectif non atteint", state))
            with r:
                rows = [{"classe": c, "n": int((validated["ValidatedClass"] == c).sum()),
                         "rappel": (validated.loc[validated["ValidatedClass"] == c, "PredictedClass"] == c).mean() * 100}
                        for c in CLASSES if (validated["ValidatedClass"] == c).any()]
                st.html('<div class="big-label">Rappel par classe (pointillés : objectif 90 %)</div>')
                ui.show(ui.recall_bars(rows), key="recall")
    st.write("")

    if not validated.empty:
        with card("confusion", "Matrice de confusion", "Classe réelle (validée) × classe prédite"):
            ui.show(ui.confusion_heatmap(validated), key="cm")


# ── Page 4 : administration (rôle admin) ────────────────────
def page_admin() -> None:
    df, err = sv.get_predictions()
    page_header("Administration", "Réglages de la chaîne d'inspection")
    if st.session_state["user"].get("role") != "admin":
        st.error("Cette page est réservée aux administrateurs.")
        return
    if err:
        db_error(err)
        return

    info = sv.threshold_info()
    current = info["value"]
    changed = (f"Modifié par {info['by']} le {info['at']:%d/%m/%Y à %H:%M} (UTC)"
               if info["by"] and info["at"] else "Valeur par défaut")

    left, right = st.columns([1, 1.4], gap="medium")
    with left, card("threshold", "Seuil de validation automatique", changed):
        st.markdown(
            f"Une prédiction dont la confiance est **supérieure ou égale** au seuil est **validée automatiquement**. "
            f"En dessous, un opérateur **doit** la valider.")
        new = st.slider("Nouveau seuil", min_value=50, max_value=99, value=int(round(current * 100)), step=1,
                        format="%d %%", key="threshold_slider") / 100
        if df.empty:
            st.caption("Pas encore d'analyses pour estimer l'impact.")
        else:
            now_todo = (df["Confidence"] < current).mean()
            new_todo = (df["Confidence"] < new).mean()
            a, b = st.columns(2)
            a.metric(f"À valider avec le seuil actuel ({current:.0%})", f"{now_todo:.0%}")
            diff = (new_todo - now_todo) * 100
            b.metric(f"À valider avec le nouveau seuil ({new:.0%})", f"{new_todo:.0%}",
                     delta=f"{diff:+.0f} pts" if abs(diff) >= 0.5 else None, delta_color="inverse")
            st.caption(f"Calculé sur les {len(df)} dernières analyses.")
        if st.button(f"Appliquer le seuil de {new:.0%}", type="primary", icon=":material/save:", width="stretch",
                     disabled=abs(new - current) < 0.005):
            sv.set_threshold(new)
            st.toast(f"Seuil enregistré : {new:.0%}", icon="✅")
            time.sleep(0.4)
            st.rerun()
    with right, card("threshold-hist", "Répartition de la confiance",
                     "En bleu : validée automatiquement · en gris : validation opérateur requise"):
        if not df.empty:
            ui.show(ui.confidence_histogram(df, height=300, threshold=new), key="admin-hist")
    st.write("")

    with card("accounts", "Comptes de l'application",
              "Gestion : python scripts/gerer_comptes.py (ajouter, reinitialiser, role, supprimer)"):
        import scot_auth
        users = scot_auth.load_users()
        if not users:
            st.info("Aucun compte configuré ici (normal en local : les comptes sont sur Azure).", icon=":material/info:")
            return
        st.dataframe(pd.DataFrame([{"Identifiant": u, "Nom": i.get("name", ""),
                                    "Rôle": "Administrateur" if i.get("role") == "admin" else "Opérateur"}
                                   for u, i in sorted(users.items())]),
                     hide_index=True, width="stretch")
