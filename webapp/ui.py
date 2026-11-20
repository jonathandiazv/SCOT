"""
SCOT — Design de l'app : palette clair/sombre, composants (cartes, indicateurs, statuts) et graphiques Plotly.

Style volontairement sobre : cartes plates à bordure fine, texte plutôt que badges,
graphiques monochromes (une couleur d'accent, du gris pour le reste). Le thème actif est
lu avec st.context.theme pour rester lisible en mode clair comme en mode sombre.
"""

import json
from contextlib import contextmanager
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ── Classes et couleurs métier (tons désaturés) ─────────────
CLASSES = ["tache", "rayure", "inclusion", "sans_defaut"]
DEFECT_CLASSES = ["tache", "rayure", "inclusion"]
LABELS = {"tache": "Tache", "rayure": "Rayure", "inclusion": "Inclusion", "sans_defaut": "Sans défaut"}
CLASS_COLORS = {"tache": "#C08A4A", "rayure": "#4C78A8", "inclusion": "#8A73B0", "sans_defaut": "#6B9E80"}

PALETTES = {
    "light": {
        "bg": "#F5F6F8", "card": "#FFFFFF", "border": "#E2E5EA", "text": "#1C2230", "muted": "#6A7282",
        "grid": "#EEF0F3", "accent": "#2F5BD3", "accent_tint": "#B9CAF4", "neutral": "#C9CED6", "track": "#EEF0F3",
        "ok": "#1F8A4C", "warn": "#B7791F", "bad": "#C53030", "image_bg": "#0E1218",
    },
    "dark": {
        "bg": "#0F1217", "card": "#161A21", "border": "#262C36", "text": "#E4E7EC", "muted": "#8B93A1",
        "grid": "#20252E", "accent": "#6D93F2", "accent_tint": "#2C4170", "neutral": "#3A414D", "track": "#20252E",
        "ok": "#4CB97A", "warn": "#D6A54A", "bad": "#E06C6C", "image_bg": "#07090C",
    },
}


def theme() -> str:
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:  # noqa: BLE001
        return "light"


def pal() -> dict:
    return PALETTES[theme()]


# ── Feuille de style ────────────────────────────────────────
def inject_css() -> None:
    p = pal()
    st.html(f"""<style>
    .stApp {{ background: {p['bg']}; }}
    .block-container {{ padding-top: 4.6rem; padding-bottom: 3rem; max-width: 1440px; }}
    h1, h2, h3 {{ letter-spacing: -0.01em; }}

    /* Cartes : tout conteneur créé avec ui.card() — plates, bordure fine */
    div[class*="st-key-card-"] {{
        background: {p['card']}; border: 1px solid {p['border']}; border-radius: 8px; padding: 16px 18px 14px;
    }}
    .card-head {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; margin-bottom:4px; }}
    .card-title {{ font-size: .95rem; font-weight: 600; color: {p['text']}; }}
    .card-sub {{ font-size: .78rem; color: {p['muted']}; margin-top: 2px; }}

    /* Indicateurs */
    .kpi {{ background:{p['card']}; border:1px solid {p['border']}; border-radius:8px; padding:14px 18px; height:100%; }}
    .kpi .l {{ font-size: .72rem; text-transform: uppercase; letter-spacing: .05em; color: {p['muted']}; font-weight: 600; }}
    .kpi .v {{ font-size: 1.65rem; font-weight: 650; color: {p['text']}; line-height: 1.2; margin-top: 6px;
               font-variant-numeric: tabular-nums; }}
    .kpi .s {{ font-size: .76rem; color: {p['muted']}; margin-top: 4px; }}

    /* Classe et statuts : du texte, pas de badges */
    .cls {{ font-weight: 600; color: {p['text']}; font-size: .86rem; }}
    .cls.lg {{ font-size: 1.6rem; font-weight: 650; line-height: 1.2; }}
    .status {{ font-size: .8rem; font-weight: 600; white-space: nowrap; }}
    .status.ok {{ color: {p['ok']}; }} .status.warn {{ color: {p['warn']}; }}
    .status.bad {{ color: {p['bad']}; }} .status.idle {{ color: {p['muted']}; font-weight: 500; }}
    .status-sep {{ color: {p['border']}; margin: 0 2px; }}

    .stat {{ font-variant-numeric: tabular-nums; }}
    .stat .v {{ font-size: 1.6rem; font-weight: 650; color: {p['text']}; line-height: 1.2; }}
    .stat .s {{ font-size: .78rem; color: {p['muted']}; margin-top: 2px; }}
    .meter {{ height: 4px; background: {p['track']}; border-radius: 2px; margin: 8px 0 4px; overflow: hidden; }}
    .meter > div {{ height: 100%; border-radius: 2px; }}

    .page-title {{ font-size: 1.4rem; font-weight: 650; color:{p['text']}; line-height:1.2; }}
    .page-sub {{ font-size: .84rem; color: {p['muted']}; margin-top: 2px; }}
    .meta {{ font-size: .78rem; color: {p['muted']}; }}
    .meta b {{ color: {p['text']}; font-weight: 600; }}
    .big-label {{ font-size:.72rem; text-transform:uppercase; letter-spacing:.05em; color:{p['muted']}; font-weight:600; }}

    /* Images */
    div[class*="st-key-card-"] [data-testid="stImage"] img {{
        border-radius: 4px; background: {p['image_bg']}; max-height: 440px; object-fit: contain;
    }}
    div[class*="st-key-thumb-"] [data-testid="stImage"] img {{
        border-radius: 4px; background: {p['image_bg']}; height: 120px; object-fit: contain;
    }}
    div[class*="st-key-thumb-"] {{ border:1px solid {p['border']}; border-radius:6px; padding:8px; }}

    /* Login */
    div.st-key-card-login {{ padding: 26px 28px 20px; }}
    .login-brand {{ text-align:center; margin-bottom: 6px; }}
    .login-brand .t {{ font-size: 1.7rem; font-weight: 700; color: {p['text']}; letter-spacing: .08em; }}
    .login-brand .s {{ font-size: .84rem; color: {p['muted']}; }}
    </style>""")


# ── Composants ──────────────────────────────────────────────
@contextmanager
def card(key: str, title: str | None = None, subtitle: str | None = None, right_html: str = ""):
    """Carte plate avec titre optionnel."""
    with st.container(key=f"card-{key}"):
        if title:
            sub = f'<div class="card-sub">{escape(subtitle)}</div>' if subtitle else ""
            st.html(f'<div class="card-head"><div><div class="card-title">{escape(title)}</div>{sub}</div>'
                    f'<div>{right_html}</div></div>')
        yield


def kpi(label: str, value: str, sub: str = "") -> None:
    sub_html = f'<div class="s">{escape(sub)}</div>' if sub else ""
    st.html(f'<div class="kpi"><div class="l">{escape(label)}</div><div class="v">{escape(value)}</div>{sub_html}</div>')


def class_pill(cls: str | None, large: bool = False) -> str:
    """Nom de la classe en texte simple."""
    if not cls:
        return ""
    return f'<span class="cls{" lg" if large else ""}">{escape(LABELS.get(cls, cls))}</span>'


def chip(text: str, state: str = "ok") -> str:
    """Statut en texte coloré (vert / ambre / rouge / gris)."""
    return f'<span class="status {state}">{escape(text)}</span>'


def stat(value: str, sub: str = "", fraction: float | None = None, state: str = "ok") -> str:
    """Grand chiffre + ligne de progression fine (remplace les jauges)."""
    p = pal()
    bar = ""
    if fraction is not None:
        color = {"ok": p["ok"], "warn": p["warn"], "bad": p["bad"], "accent": p["accent"]}.get(state, p["accent"])
        bar = (f'<div class="meter"><div style="width:{max(0.0, min(fraction, 1.0)) * 100:.1f}%;'
               f'background:{color}"></div></div>')
    sub_html = f'<div class="s">{escape(sub)}</div>' if sub else ""
    return f'<div class="stat"><div class="v">{escape(value)}</div>{bar}{sub_html}</div>'


def confidence_state(conf: float) -> str:
    return "ok" if conf >= 0.8 else "warn" if conf >= 0.5 else "bad"


def parse_probs(probabilities_json) -> dict:
    try:
        probs = json.loads(probabilities_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return {c: probs.get(c, 0.0) for c in CLASSES if c in probs}


# ── Graphiques ──────────────────────────────────────────────
def _layout(fig: go.Figure, height: int, legend: bool = False) -> go.Figure:
    p = pal()
    fig.update_layout(
        height=height, margin=dict(l=4, r=8, t=8, b=4),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Source Sans Pro, Segoe UI, sans-serif", size=12, color=p["muted"]),
        showlegend=legend, hoverlabel=dict(bgcolor=p["card"], bordercolor=p["border"], font_color=p["text"]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=p["muted"], size=11),
                    itemsizing="constant"),
        bargap=0.35,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, showline=True, linecolor=p["border"],
                     tickfont=dict(color=p["muted"], size=11), ticks="", automargin=True)
    fig.update_yaxes(gridcolor=p["grid"], gridwidth=1, zeroline=False, showline=False,
                     tickfont=dict(color=p["muted"], size=11), automargin=True, ticksuffix="  ")
    return fig


def show(fig: go.Figure, key: str | None = None) -> None:
    st.plotly_chart(fig, width="stretch", theme=None, key=key, config={"displayModeBar": False, "responsive": True})


def _hbar(labels: list, values: list, colors: list, text: list, height: int, x_max: float = 100) -> go.Figure:
    """Barres horizontales fines, sans fond ni axe : valeurs écrites au bout."""
    p = pal()
    fig = go.Figure(go.Bar(y=labels, x=values, orientation="h", marker=dict(color=colors), width=0.42,
                           text=text, textposition="outside", cliponaxis=False,
                           textfont=dict(color=p["text"], size=12), hovertemplate="%{y} : %{text}<extra></extra>"))
    _layout(fig, height)
    fig.update_xaxes(range=[0, x_max * 1.18], visible=False)
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(color=p["text"], size=12))
    return fig


def proba_bars(probs: dict, height: int = 170) -> go.Figure:
    """Probabilités par classe : la classe retenue en couleur d'accent, les autres en gris."""
    p = pal()
    classes = [c for c in CLASSES if c in probs]
    top = max(classes, key=lambda c: probs[c]) if classes else None
    values = [probs[c] * 100 for c in classes]
    return _hbar([LABELS[c] for c in classes], values,
                 [p["accent"] if c == top else p["neutral"] for c in classes],
                 [f"{v:.1f} %" for v in values], height)


def class_bars(counts: pd.Series, height: int = 230) -> go.Figure:
    """Répartition des détections par classe (remplace le donut)."""
    p = pal()
    counts = counts.reindex(CLASSES, fill_value=0)
    total = max(int(counts.sum()), 1)
    return _hbar([LABELS[c] for c in CLASSES], list(counts.values), [p["accent"]] * len(CLASSES),
                 [f"{int(n)}  ·  {n / total:.0%}" for n in counts.values], height, x_max=max(counts.max(), 1))


def timeline(df: pd.DataFrame, height: int = 260) -> go.Figure:
    """Détections par jour, empilées par classe (tons désaturés)."""
    d = df.assign(Jour=df["Local"].dt.tz_localize(None).dt.floor("D"))
    t = d.pivot_table(index="Jour", columns="PredictedClass", values="Id", aggfunc="count", fill_value=0)
    if len(t.index):
        t = t.reindex(pd.date_range(t.index.min(), t.index.max(), freq="D"), fill_value=0)
    fig = go.Figure()
    for c in CLASSES:
        if c in t.columns:
            fig.add_bar(x=t.index, y=t[c], name=LABELS[c], marker=dict(color=CLASS_COLORS[c]),
                        hovertemplate=f"{LABELS[c]} : %{{y}}<extra>%{{x|%d/%m}}</extra>")
    _layout(fig, height, legend=True)
    fig.update_layout(barmode="stack", bargap=0.55)
    fig.update_xaxes(tickformat="%d/%m")
    fig.update_yaxes(rangemode="tozero")
    return fig


def confidence_histogram(df: pd.DataFrame, height: int = 240, threshold: float | None = None) -> go.Figure:
    """Nombre d'images par tranche de 10 % de confiance.

    Avec seuil : tranches au-dessus du seuil en couleur d'accent (validation automatique),
    en dessous en gris (validation opérateur), et une ligne fine marque le seuil.
    """
    p = pal()
    edges = list(range(0, 101, 10))
    counts = pd.cut(df["Confidence"] * 100, bins=edges, include_lowest=True, right=True).value_counts(sort=False)
    labels = [f"{a}–{b}" for a, b in zip(edges[:-1], edges[1:])]
    thr = 0.8 if threshold is None else threshold
    colors = [p["accent"] if a >= thr * 100 else p["neutral"] for a in edges[:-1]]
    fig = go.Figure(go.Bar(x=labels, y=counts.values, marker=dict(color=colors), width=0.6,
                           hovertemplate="%{x} % : %{y} image(s)<extra></extra>"))
    if threshold is not None:
        fig.add_vline(x=threshold * 10 - 0.5, line=dict(color=p["muted"], width=1, dash="dot"),
                      annotation=dict(text=f"seuil {threshold:.0%}", font=dict(color=p["muted"], size=11),
                                      yanchor="bottom"), annotation_position="top")
    _layout(fig, height)
    if threshold is not None:
        fig.update_layout(margin=dict(t=26))
    fig.update_xaxes(tickangle=0, title=dict(text="confiance (%)", font=dict(size=11, color=p["muted"])))
    fig.update_yaxes(rangemode="tozero")
    return fig


def recall_bars(rows: list[dict], height: int = 200) -> go.Figure:
    """Rappel par classe : vert si ≥ 90 %, rouge sinon."""
    p = pal()
    fig = _hbar([f"{LABELS[r['classe']]} (n={r['n']})" for r in rows], [r["rappel"] for r in rows],
                [p["ok"] if r["rappel"] >= 90 else p["bad"] for r in rows],
                [f"{r['rappel']:.0f} %" for r in rows], height)
    fig.add_vline(x=90, line=dict(color=p["muted"], width=1, dash="dot"))
    return fig


def confusion_heatmap(validated: pd.DataFrame, height: int = 300) -> go.Figure:
    p = pal()
    ct = pd.crosstab(validated["ValidatedClass"], validated["PredictedClass"]).reindex(
        index=CLASSES, columns=CLASSES, fill_value=0)
    fig = go.Figure(go.Heatmap(
        z=ct.values, x=[LABELS[c] for c in CLASSES], y=[LABELS[c] for c in CLASSES],
        colorscale=[[0, p["card"]], [1, p["accent_tint"]]], showscale=False,
        text=ct.values, texttemplate="%{text}", textfont=dict(size=14, color=p["text"]),
        hovertemplate="Réel %{y} → prédit %{x} : %{z}<extra></extra>", xgap=2, ygap=2))
    _layout(fig, height)
    fig.update_xaxes(title=dict(text="Prédit", font=dict(color=p["muted"])), side="top", showline=False)
    fig.update_yaxes(title=dict(text="Réel", font=dict(color=p["muted"])), autorange="reversed", showgrid=False,
                     ticks="", ticksuffix="   ")
    return fig
