import streamlit as st
import torch
from PIL import Image
import os
import time
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

# Importation des fonctions de prédiction
from predict import load_model, preprocess, predict, COLORS

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="SCOT - Système de Contrôle Optique",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- STYLE CSS PERSONNALISÉ (MODE CLAIR) ---
st.markdown("""
    <style>
    /* Global Background and Text */
    .stApp {
        background-color: #FFFFFF;
        color: #1F2937;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: #F3F4F6;
        border-right: 1px solid #E5E7EB;
    }
    
    /* Headers styling */
    h1, h2, h3 {
        color: #111827 !important;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-weight: 700;
    }
    
    /* Custom Card Style */
    .status-card {
        padding: 24px;
        border-radius: 8px;
        background-color: #F9FAFB;
        border: 1px solid #E5E7EB;
        margin-bottom: 20px;
    }
    
    .metric-label {
        color: #6B7280;
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    .metric-value {
        color: #111827;
        font-size: 2rem;
        font-weight: 800;
    }

    /* Status indicators */
    .border-success { border-left: 6px solid #10B981; }
    .border-warning { border-left: 6px solid #F59E0B; }
    .border-danger { border-left: 6px solid #EF4444; }
    
    /* Buttons customization (Bleu Industriel) */
    div.stButton > button:first-child {
        background-color: #2563EB;
        color: white;
        border-radius: 6px;
        border: none;
        padding: 0.5rem 1rem;
        font-weight: 600;
        width: 100%;
    }
    
    div.stButton > button:hover {
        background-color: #1D4ED8;
        color: white;
        border: none;
    }

    /* Logo placeholder style */
    .logo-container {
        font-size: 2.5rem;
        font-weight: 900;
        color: #2563EB;
        letter-spacing: -2px;
        margin-bottom: 0px;
        padding-bottom: 0px;
    }
    .logo-sub {
        font-size: 0.8rem;
        color: #6B7280;
        margin-top: -10px;
        font-weight: 500;
    }
    </style>
    """, unsafe_allow_html=True)

# --- INITIALISATION SESSION STATE ---
if 'history' not in st.session_state:
    st.session_state.history = []

# --- FONCTIONS UTILITAIRES ---
@st.cache_resource
def get_cached_model(path, dev):
    if Path(path).exists():
        try:
            return load_model(path, dev)
        except Exception as e:
            st.error(f"Erreur de chargement du modèle : {e}")
            return None, None, None
    return None, None, None

def get_model_options():
    output_dir = "outputs"
    archive_dir = os.path.join(output_dir, "models_archive")
    default_model = os.path.join(output_dir, "best_model.pth")
    
    options = {}
    if os.path.exists(default_model):
        options["Production (Dernier meilleur)"] = default_model
    
    if os.path.exists(archive_dir):
        archived = sorted([f for f in os.listdir(archive_dir) if f.endswith(".pth")], reverse=True)
        for f in archived:
            options[f"Archive : {f}"] = os.path.join(archive_dir, f)
            
    return options

def main():
    # --- SIDEBAR ---
    with st.sidebar:
        st.markdown('<div class="logo-container">SCOT</div>', unsafe_allow_html=True)
        st.markdown('<div class="logo-sub">Système de Contrôle Optique des Traces</div>', unsafe_allow_html=True)
        st.divider()
        
        st.subheader("Configuration")
        model_options = get_model_options()
        
        if not model_options:
            st.error("Aucun modèle détecté dans le dossier /outputs.")
            st.stop()
            
        selected_model_label = st.selectbox("Modèle d'IA", list(model_options.keys()))
        model_path = model_options[selected_model_label]
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        st.caption(f"Hardware : {device.upper()} | Fichier : {os.path.basename(model_path)}")
        
        st.divider()
        
        st.subheader("Surveillance")
        auto_refresh = st.toggle("Mode Temps Réel (Auto-Scan)", value=False)
        refresh_interval = st.slider("Intervalle (secondes)", 2, 30, 10) if auto_refresh else 10
        
        st.divider()
        if st.button("Effacer l'historique", use_container_width=True):
            st.session_state.history = []
            st.rerun()

    # --- CHARGEMENT DU MODÈLE ---
    model, classes, cfg = get_cached_model(model_path, device)
    
    # --- HEADER PRINCIPAL ---
    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.title("Tableau de Bord - Inspection")
    with col_h2:
        st.write("") 
        if st.button("Rafraîchir Manuellement", use_container_width=True):
            st.rerun()

    # --- LOGIQUE D'ACQUISITION ---
    camera_dir = "data_camera"
    os.makedirs(camera_dir, exist_ok=True)
    
    exts = ('.png', '.jpg', '.jpeg', '.bmp')
    files = [os.path.join(camera_dir, f) for f in os.listdir(camera_dir) if f.lower().endswith(exts)]
    latest_file = max(files, key=os.path.getmtime) if files else None

    # --- ONGLETS ---
    tab_inspect, tab_history, tab_stats = st.tabs(["Inspection Directe", "Historique des Détections", "Statistiques de Session"])

    with tab_inspect:
        if latest_file:
            col_img, col_res = st.columns([3, 2])
            
            with col_img:
                st.subheader("Capture Courante")
                # Les images ont un fond noir, on les affiche sans bordure pour un rendu propre
                image = Image.open(latest_file)
                st.image(image, caption=f"Fichier : {os.path.basename(latest_file)}", use_container_width=True)
                
            with col_res:
                st.subheader("Diagnostic IA")
                with st.spinner('Analyse de l\'image...'):
                    # Inférence
                    tensor, img_pil = preprocess(latest_file, cfg.get("img_size", 128))
                    pred_class, probs = predict(model, tensor, classes, device)
                    confiance = probs.max()
                    
                    # Style en fonction de la confiance
                    border_class = "border-success" if confiance > 0.8 else "border-warning" if confiance > 0.5 else "border-danger"
                    
                    st.markdown(f"""
                        <div class="status-card {border_class}">
                            <div class="metric-label">Type de Défaut Détecté</div>
                            <div class="metric-value" style="color: {COLORS.get(pred_class, '#111827')};">{pred_class.upper()}</div>
                            <hr style="border: 0.5px solid #E5E7EB; margin: 15px 0;">
                            <div class="metric-label">Indice de Confiance</div>
                            <div class="metric-value">{confiance:.1%}</div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # Graphique des probabilités
                    fig, ax = plt.subplots(figsize=(6, 3))
                    fig.patch.set_facecolor('#FFFFFF')
                    ax.set_facecolor('#F9FAFB')
                    
                    bar_colors = [COLORS.get(c, '#6B7280') for c in classes]
                    ax.barh(classes, probs * 100, color=bar_colors)
                    ax.set_xlim(0, 100)
                    ax.tick_params(colors='#374151', labelsize=9)
                    ax.spines[:].set_visible(False)
                    ax.grid(axis='x', color='#E5E7EB', linestyle='--', alpha=0.7)
                    st.pyplot(fig)

                    # Mise à jour de l'historique
                    new_entry = {
                        "Horodatage": time.strftime("%H:%M:%S"),
                        "Fichier": os.path.basename(latest_file),
                        "Détection": pred_class.upper(),
                        "Confiance": f"{confiance:.1%}"
                    }
                    if not st.session_state.history or st.session_state.history[0]["Fichier"] != new_entry["Fichier"]:
                        st.session_state.history.insert(0, new_entry)
                        if len(st.session_state.history) > 50: st.session_state.history.pop()

        else:
            st.info("Information : En attente de nouvelles images dans le dossier data_camera.")
            if st.button("Simuler une capture"):
                import shutil
                val_images = list(Path("dataset/val").rglob("*.png"))
                if val_images:
                    shutil.copy(val_images[np.random.randint(len(val_images))], os.path.join(camera_dir, f"sim_{int(time.time())}.png"))
                    st.rerun()

    with tab_history:
        st.subheader("Journal des Analyses")
        if st.session_state.history:
            df = pd.DataFrame(st.session_state.history)
            st.table(df)
        else:
            st.write("Aucun historique disponible pour cette session.")

    with tab_stats:
        st.subheader("Analyse de Session")
        if st.session_state.history:
            df = pd.DataFrame(st.session_state.history)
            counts = df["Détection"].value_counts()
            
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Répartition des Défauts**")
                # Utilisation de bar_chart natif pour une meilleure intégration mode clair
                st.bar_chart(counts)
            with c2:
                st.markdown("**Indicateurs Clés**")
                st.metric("Total Analysé", len(df))
                st.metric("Défaut Dominant", counts.index[0] if not counts.empty else "N/A")
        else:
            st.info("Les statistiques seront disponibles après les premières détections.")

    # --- LOGIQUE AUTO-REFRESH ---
    if auto_refresh:
        placeholder = st.empty()
        for i in range(refresh_interval, 0, -1):
            placeholder.caption(f"Actualisation dans {i} secondes...")
            time.sleep(1)
        st.rerun()

if __name__ == "__main__":
    main()
