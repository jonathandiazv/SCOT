"""
SCOT — Design de l'app : palette clair/sombre, composants (cartes, KPI, badges) et graphiques Plotly.

Le thème actif est lu avec st.context.theme : chaque composant et chaque graphique
prend ses couleurs dans la palette correspondante, pour rester lisible dans les deux modes.
"""

import base64
import json
from contextlib import contextmanager
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ── Classes et couleurs métier ──────────────────────────────
CLASSES = ["tache", "rayure", "inclusion", "sans_defaut"]
DEFECT_CLASSES = ["tache", "rayure", "inclusion"]
LABELS = {"tache": "Tache", "rayure": "Rayure", "inclusion": "Inclusion", "sans_defaut": "Sans défaut"}
CLASS_COLORS = {"tache": "#F97316", "rayure": "#0EA5E9", "inclusion": "#8B5CF6", "sans_defaut": "#10B981"}

PALETTES = {
    "light": {
        "bg": "#F3F5FA", "card": "#FFFFFF", "border": "#E1E6EF", "text": "#1B2433", "muted": "#6B7588",
        "grid": "#EDF0F6", "accent": "#3563E9", "accent_soft": "#E8EEFD", "track": "#E9EDF4",
        "shadow": "0 1px 2px rgba(16,24,40,.04), 0 6px 20px rgba(16,24,40,.06)",
        "ok": "#10B981", "warn": "#F59E0B", "bad": "#EF4444", "image_bg": "#0B1120",
    },
    "dark": {
        "bg": "#0B1120", "card": "#131C2E", "border": "#24324C", "text": "#E5EAF2", "muted": "#93A0B8",
        "grid": "#1E2A40", "accent": "#5B8CFF", "accent_soft": "#1B2A4A", "track": "#22304A",
        "shadow": "0 1px 2px rgba(0,0,0,.35), 0 8px 24px rgba(0,0,0,.25)",
        "ok": "#34D399", "warn": "#FBBF24", "bad": "#F87171", "image_bg": "#05080F",
    },
}

# Icônes (Lucide, licence ISC) — tracés SVG
ICONS = {
    "image": '<rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>',
    "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "clipboard": '<rect width="8" height="4" x="8" y="2" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
    "gauge": '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
    "zap": '<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>',
    "check": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "pencil": '<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
}


def theme() -> str:
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:  # noqa: BLE001
        return "light"


def pal() -> dict:
    return PALETTES[theme()]


def icon(name: str, size: int = 22, color: str = "#fff") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" '
            f'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            f'{ICONS[name]}</svg>')


# ── Feuille de style ────────────────────────────────────────
def inject_css() -> None:
    p = pal()
    st.html(f"""<style>
    .stApp {{ background: {p['bg']}; }}
    .block-container {{ padding-top: 4.6rem; padding-bottom: 3rem; max-width: 1440px; }}
    h1, h2, h3 {{ letter-spacing: -0.01em; }}

    /* Cartes : tout conteneur créé avec ui.card() */
    div[class*="st-key-card-"] {{
        background: {p['card']}; border: 1px solid {p['border']}; border-radius: 16px;
        padding: 18px 20px 16px; box-shadow: {p['shadow']};
    }}
    .card-head {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; margin-bottom:2px; }}
    .card-title {{ font-size: 1.02rem; font-weight: 650; color: {p['text']}; }}
    .card-sub {{ font-size: .8rem; color: {p['muted']}; margin-top: 2px; }}

    /* KPI */
    .kpi {{ display:flex; align-items:center; justify-content:space-between; gap:12px;
            background:{p['card']}; border:1px solid {p['border']}; border-radius:16px;
            padding:18px 20px; box-shadow:{p['shadow']}; height:100%; }}
    .kpi .v {{ font-size: 1.75rem; font-weight: 700; color: {p['text']}; line-height: 1.15;
               font-variant-numeric: tabular-nums; }}
    .kpi .l {{ font-size: .84rem; color: {p['muted']}; margin-top: 3px; }}
    .kpi .s {{ font-size: .75rem; color: {p['muted']}; margin-top: 6px; }}
    .kpi .ic {{ flex: 0 0 52px; width:52px; height:52px; border-radius:50%; display:grid; place-items:center; }}

    /* Badges et pastilles d'état */
    .pill {{ display:inline-flex; align-items:center; gap:6px; padding:3px 11px; border-radius:999px;
             font-weight:650; font-size:.78rem; white-space:nowrap; }}
    .pill.lg {{ font-size: 1.05rem; padding: 6px 16px; }}
    .chip {{ display:inline-flex; align-items:center; gap:7px; padding:5px 12px; border-radius:999px;
             background:{p['card']}; border:1px solid {p['border']}; font-size:.8rem; color:{p['text']}; white-space:nowrap; }}
    .dot {{ width:8px; height:8px; border-radius:50%; display:inline-block; }}
    .page-title {{ font-size: 1.55rem; font-weight: 700; color:{p['text']}; line-height:1.2; }}
    .page-sub {{ font-size: .86rem; color: {p['muted']}; margin-top: 2px; }}
    .meta {{ font-size: .8rem; color: {p['muted']}; }}
    .meta b {{ color: {p['text']}; font-weight: 600; }}
    .big-label {{ font-size:.74rem; text-transform:uppercase; letter-spacing:.06em; color:{p['muted']}; font-weight:600; }}

    /* Images : fond sombre, coins arrondis, hauteur maîtrisée */
    div[class*="st-key-card-"] [data-testid="stImage"] img {{
        border-radius: 12px; background: {p['image_bg']}; max-height: 440px; object-fit: contain;
    }}
    div[class*="st-key-thumb-"] [data-testid="stImage"] img {{
        border-radius: 10px; background: {p['image_bg']}; height: 120px; object-fit: contain;
    }}
    div[class*="st-key-thumb-"] {{
        background:{p['card']}; border:1px solid {p['border']}; border-radius:14px; padding:10px; box-shadow:{p['shadow']};
    }}

    /* Login */
    div.st-key-card-login {{ padding: 28px 30px 22px; }}
    .login-brand {{ text-align:center; margin-bottom: 6px; }}
    .login-brand .t {{ font-size: 1.9rem; font-weight: 800; color: {p['accent']}; letter-spacing: .04em; }}
    .login-brand .s {{ font-size: .85rem; color: {p['muted']}; }}
    </style>""")


# ── Composants ──────────────────────────────────────────────
@contextmanager
def card(key: str, title: str | None = None, subtitle: str | None = None, right_html: str = ""):
    """Carte blanche (claire) ou ardoise (sombre) avec titre optionnel."""
    with st.container(key=f"card-{key}"):
        if title:
            sub = f'<div class="card-sub">{escape(subtitle)}</div>' if subtitle else ""
            st.html(f'<div class="card-head"><div><div class="card-title">{escape(title)}</div>{sub}</div>'
                    f'<div>{right_html}</div></div>')
        yield


def icon_bg(name: str, size: int = 24, color: str = "#fff") -> str:
    """Icône en image de fond CSS (Streamlit filtre les balises <svg> directes)."""
    b64 = base64.b64encode(icon(name, size, color).encode()).decode()
    return f"url('data:image/svg+xml;base64,{b64}') center / {size}px no-repeat"


def kpi(label: str, value: str, icon_name: str, color: str, sub: str = "") -> None:
    sub_html = f'<div class="s">{escape(sub)}</div>' if sub else ""
    st.html(f'<div class="kpi"><div><div class="v">{escape(value)}</div><div class="l">{escape(label)}</div>{sub_html}</div>'
            f'<div class="ic" style="background:{icon_bg(icon_name)}, {color}"></div></div>')


def class_pill(cls: str | None, large: bool = False) -> str:
    if not cls:
        return ""
    c = CLASS_COLORS.get(cls, pal()["muted"])
    return (f'<span class="pill{" lg" if large else ""}" style="background:{c}22;color:{c}">'
            f'<span class="dot" style="background:{c}"></span>{escape(LABELS.get(cls, cls))}</span>')


def chip(text: str, state: str = "ok") -> str:
    p = pal()
    color = {"ok": p["ok"], "warn": p["warn"], "bad": p["bad"], "idle": p["muted"]}[state]
    return f'<span class="chip"><span class="dot" style="background:{color}"></span>{escape(text)}</span>'


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
        height=height, margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Source Sans Pro, Segoe UI, sans-serif", size=12, color=p["muted"]),
        showlegend=legend, hoverlabel=dict(bgcolor=p["card"], bordercolor=p["border"], font_color=p["text"]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=p["text"])),
    )
    fig.update_xaxes(gridcolor=p["grid"], zeroline=False, linecolor=p["border"], tickfont=dict(color=p["muted"]),
                     automargin=True)
    fig.update_yaxes(gridcolor=p["grid"], zeroline=False, linecolor=p["border"], tickfont=dict(color=p["muted"]),
                     automargin=True, ticksuffix="  ")
    return fig


def show(fig: go.Figure, key: str | None = None) -> None:
    st.plotly_chart(fig, width="stretch", theme=None, key=key, config={"displayModeBar": False, "responsive": True})


def proba_bars(probs: dict, height: int = 190) -> go.Figure:
    p = pal()
    classes = [c for c in reversed(CLASSES) if c in probs]
    values = [probs[c] * 100 for c in classes]
    fig = go.Figure()
    fig.add_bar(y=[LABELS[c] for c in classes], x=[100] * len(classes), orientation="h",
                marker=dict(color=p["track"]), hoverinfo="skip", width=0.55)
    fig.add_bar(y=[LABELS[c] for c in classes], x=values, orientation="h", width=0.55,
                marker=dict(color=[CLASS_COLORS[c] for c in classes]),
                text=[f"{v:.1f} %" for v in values], textposition="outside", cliponaxis=False,
                textfont=dict(color=p["text"], size=12), hovertemplate="%{y} : %{x:.1f} %<extra></extra>")
    fig.update_layout(barmode="overlay")
    _layout(fig, height)
    fig.update_xaxes(range=[0, 118], visible=False)
    fig.update_yaxes(tickfont=dict(color=p["text"], size=13), gridcolor="rgba(0,0,0,0)")
    return fig


def gauge(value: float, title: str, color: str, height: int = 190, suffix: str = " %",
          target: float | None = None, max_value: float = 100) -> go.Figure:
    p = pal()
    g = dict(axis=dict(range=[0, max_value], tickwidth=0, tickcolor=p["muted"], tickfont=dict(color=p["muted"], size=10)),
             bar=dict(color=color, thickness=0.28), bgcolor=p["track"], borderwidth=0)
    if target is not None:
        g["threshold"] = dict(line=dict(color=p["text"], width=3), thickness=0.8, value=target)
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value, gauge=g,
        number=dict(suffix=suffix, font=dict(size=34, color=p["text"]), valueformat=".1f"),
        title=dict(text=title, font=dict(size=13, color=p["muted"])),
        domain=dict(x=[0, 1], y=[0, 1])))
    _layout(fig, height)
    fig.update_layout(margin=dict(l=24, r=24, t=36, b=4))
    return fig


def donut(counts: pd.Series, height: int = 280) -> go.Figure:
    p = pal()
    counts = counts.reindex(CLASSES, fill_value=0)
    counts = counts[counts > 0]
    fig = go.Figure(go.Pie(
        labels=[LABELS[c] for c in counts.index], values=counts.values, hole=0.68, sort=False,
        marker=dict(colors=[CLASS_COLORS[c] for c in counts.index], line=dict(color=p["card"], width=3)),
        textinfo="none", hovertemplate="%{label} : %{value} (%{percent})<extra></extra>"))
    fig.add_annotation(text=f"<b>{int(counts.sum())}</b><br><span style='font-size:12px'>images</span>",
                       showarrow=False, font=dict(size=26, color=p["text"]))
    _layout(fig, height, legend=True)
    fig.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.02, x=0.5, xanchor="center"))
    return fig


def timeline(df: pd.DataFrame, height: int = 280) -> go.Figure:
    """Détections par jour, empilées par classe."""
    p = pal()
    d = df.assign(Jour=df["Local"].dt.tz_localize(None).dt.floor("D"))
    t = d.pivot_table(index="Jour", columns="PredictedClass", values="Id", aggfunc="count", fill_value=0)
    if len(t.index):
        t = t.reindex(pd.date_range(t.index.min(), t.index.max(), freq="D"), fill_value=0)
    fig = go.Figure()
    for c in CLASSES:
        if c in t.columns:
            fig.add_bar(x=t.index, y=t[c], name=LABELS[c], marker=dict(color=CLASS_COLORS[c]),
                        hovertemplate=f"{LABELS[c]} : %{{y}}<extra>%{{x|%d/%m}}</extra>")
    fig.update_layout(barmode="stack", bargap=0.45)
    _layout(fig, height, legend=True)
    fig.update_xaxes(tickformat="%d/%m", showgrid=False)
    fig.update_yaxes(rangemode="tozero")
    return fig


def confidence_histogram(df: pd.DataFrame, height: int = 260, threshold: float | None = None) -> go.Figure:
    """Nombre d'images par tranche de 10 % de confiance.

    Sans seuil : rouge < 50 %, orange 50–80 %, vert au-delà. Avec seuil : vert = validation
    automatique, orange = validation opérateur requise, et une ligne marque le seuil.
    """
    p = pal()
    edges = list(range(0, 101, 10))
    counts = pd.cut(df["Confidence"] * 100, bins=edges, include_lowest=True, right=True).value_counts(sort=False)
    labels = [f"{a}–{b} %" for a, b in zip(edges[:-1], edges[1:])]
    if threshold is None:
        colors = [p["bad"] if a < 50 else p["warn"] if a < 80 else p["ok"] for a in edges[:-1]]
    else:
        colors = [p["ok"] if a >= threshold * 100 else p["warn"] for a in edges[:-1]]
    fig = go.Figure(go.Bar(x=labels, y=counts.values, marker=dict(color=colors), width=0.7,
                           hovertemplate="%{x} : %{y} image(s)<extra></extra>"))
    if threshold is not None:
        x = threshold * 10 - 0.5  # position du seuil sur l'axe des tranches (une tranche = 10 %)
        fig.add_vline(x=x, line=dict(color=p["text"], width=2, dash="dash"),
                      annotation=dict(text=f"seuil {threshold:.0%}", font=dict(color=p["text"]), yanchor="bottom"),
                      annotation_position="top")
    _layout(fig, height)
    if threshold is not None:
        fig.update_layout(margin=dict(t=30))
    fig.update_xaxes(showgrid=False, tickangle=0, tickfont=dict(size=10))
    fig.update_yaxes(rangemode="tozero")
    return fig


def recall_bars(rows: list[dict], height: int = 230) -> go.Figure:
    p = pal()
    fig = go.Figure()
    labels = [LABELS[r["classe"]] for r in rows]
    fig.add_bar(y=labels, x=[100] * len(rows), orientation="h", marker=dict(color=p["track"]),
                hoverinfo="skip", width=0.5)
    fig.add_bar(y=labels, x=[r["rappel"] for r in rows], orientation="h", width=0.5,
                marker=dict(color=[CLASS_COLORS[r["classe"]] for r in rows]),
                text=[f"{r['rappel']:.0f} %  ({r['n']})" for r in rows], textposition="outside", cliponaxis=False,
                textfont=dict(color=p["text"]), hovertemplate="%{y} : %{x:.0f} %<extra></extra>")
    fig.add_vline(x=90, line=dict(color=p["text"], width=1.5, dash="dot"))
    fig.update_layout(barmode="overlay")
    _layout(fig, height)
    fig.update_xaxes(range=[0, 125], visible=False)
    fig.update_yaxes(autorange="reversed", tickfont=dict(color=p["text"], size=13), gridcolor="rgba(0,0,0,0)")
    return fig


def confusion_heatmap(validated: pd.DataFrame, height: int = 300) -> go.Figure:
    p = pal()
    ct = pd.crosstab(validated["ValidatedClass"], validated["PredictedClass"]).reindex(
        index=CLASSES, columns=CLASSES, fill_value=0)
    fig = go.Figure(go.Heatmap(
        z=ct.values, x=[LABELS[c] for c in CLASSES], y=[LABELS[c] for c in CLASSES],
        colorscale=[[0, p["track"]], [1, p["accent"] if theme() == "dark" else "#9DB8F9"]], showscale=False,
        text=ct.values, texttemplate="%{text}", textfont=dict(size=15, color=p["text"]),
        hovertemplate="Réel %{y} → prédit %{x} : %{z}<extra></extra>", xgap=4, ygap=4))
    _layout(fig, height)
    fig.update_xaxes(title=dict(text="Prédit", font=dict(color=p["muted"])), side="top", showgrid=False)
    fig.update_yaxes(title=dict(text="Réel", font=dict(color=p["muted"])), autorange="reversed", showgrid=False)
    return fig
