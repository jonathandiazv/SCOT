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
    page_title="ParticleScope - Industrial AI",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- STYLE CSS PERSONNALISÉ ---
st.markdown("""
    <style>
    /* Global Background and Text */
    .stApp {
        background-color: #0e1117;
        color: #e0e0e0;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: #161b22;
        border-right: 1px solid #30363d;
    }
    
    /* Headers styling */
    h1, h2, h3 {
        color: #58a6ff !important;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    
    /* Custom Card Style */
    .status-card {
        padding: 20px;
        border-radius: 12px;
        background-color: #161b22;
        border: 1px solid #30363d;
        margin-bottom: 20px;
    }
    
    .metric-label {
        color: #8b949e;
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    .metric-value {
        color: #ffffff;
        font-size: 1.8rem;
        font-weight: bold;
    }

    /* Success/Warning border indicators */
    .border-success { border-left: 5px solid #238636; }
    .border-warning { border-left: 5px solid #d29922; }
    .border-danger { border-left: 5px solid #f85149; }
    
    /* Buttons customization */
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
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
            st.error(f"Erreur de chargement : {e}")
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
        st.image("https://img.icons8.com/fluency/96/microscope.png", width=80)
        st.title("ParticleScope")
        st.markdown("*Système Intelligent de Contrôle Qualité*")
        st.divider()
        
        st.header("⚙️ Configuration")
        model_options = get_model_options()
        
        if not model_options:
            st.error("Aucun modèle détecté dans `/outputs`.")
            st.stop()
            
        selected_model_label = st.selectbox("Modèle d'IA", list(model_options.keys()))
        model_path = model_options[selected_model_label]
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        st.caption(f"Hardware: `{device.upper()}` | Model: `{os.path.basename(model_path)}`")
        
        st.divider()
        
        st.header("🔄 Surveillance")
        auto_refresh = st.toggle("Mode Temps Réel (Auto-Scan)", value=False)
        refresh_interval = st.slider("Intervalle (s)", 2, 30, 10) if auto_refresh else 10
        
        st.divider()
        if st.button("🗑️ Effacer l'historique", use_container_width=True):
            st.session_state.history = []
            st.rerun()

    # --- CHARGEMENT DU MODÈLE ---
    model, classes, cfg = get_cached_model(model_path, device)
    
    # --- HEADER PRINCIPAL ---
    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.title("🔬 Tableau de Bord - Inspection")
    with col_h2:
        st.write("") # Padding
        if st.button("🔄 Rafraîchir Manuellement", use_container_width=True):
            st.rerun()

    # --- LOGIQUE D'ACQUISITION ---
    camera_dir = "data_camera"
    os.makedirs(camera_dir, exist_ok=True)
    
    exts = ('.png', '.jpg', '.jpeg', '.bmp')
    files = [os.path.join(camera_dir, f) for f in os.listdir(camera_dir) if f.lower().endswith(exts)]
    latest_file = max(files, key=os.path.getmtime) if files else None

    # --- TABS ---
    tab_inspect, tab_history, tab_stats = st.tabs(["🔍 Inspection Directe", "📜 Historique", "📊 Statistiques"])

    with tab_inspect:
        if latest_file:
            col_img, col_res = st.columns([3, 2])
            
            with col_img:
                st.subheader("Flux d'acquisition")
                image = Image.open(latest_file)
                st.image(image, caption=f"Fichier : {os.path.basename(latest_file)}", use_container_width=True)
                
            with col_res:
                st.subheader("Diagnostic IA")
                with st.spinner('Analyse en cours...'):
                    # Inférence
                    tensor, img_pil = preprocess(latest_file, cfg.get("img_size", 128))
                    pred_class, probs = predict(model, tensor, classes, device)
                    confiance = probs.max()
                    
                    # Style en fonction de la confiance
                    border_class = "border-success" if confiance > 0.8 else "border-warning" if confiance > 0.5 else "border-danger"
                    
                    st.markdown(f"""
                        <div class="status-card {border_class}">
                            <div class="metric-label">Résultat Détecté</div>
                            <div class="metric-value" style="color: {COLORS.get(pred_class, '#fff')};">{pred_class.upper()}</div>
                            <hr style="border: 0.5px solid #30363d; margin: 15px 0;">
                            <div class="metric-label">Indice de Confiance</div>
                            <div class="metric-value">{confiance:.1%}</div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # Graphique des probabilités
                    fig, ax = plt.subplots(figsize=(6, 3))
                    fig.patch.set_facecolor('#161b22')
                    ax.set_facecolor('#161b22')
                    
                    bar_colors = [COLORS.get(c, '#888') for c in classes]
                    ax.barh(classes, probs * 100, color=bar_colors)
                    ax.set_xlim(0, 100)
                    ax.tick_params(colors='#8b949e', labelsize=8)
                    ax.spines[:].set_visible(False)
                    ax.grid(axis='x', color='#30363d', linestyle='--', alpha=0.5)
                    st.pyplot(fig)

                    # Mise à jour de l'historique
                    new_entry = {
                        "Time": time.strftime("%H:%M:%S"),
                        "File": os.path.basename(latest_file),
                        "Detection": pred_class.upper(),
                        "Confidence": f"{confiance:.1%}"
                    }
                    if not st.session_state.history or st.session_state.history[0]["File"] != new_entry["File"]:
                        st.session_state.history.insert(0, new_entry)
                        if len(st.session_state.history) > 50: st.session_state.history.pop()

        else:
            st.info("💡 En attente d'images dans le dossier `data_camera/`...")
            if st.button("🚀 Simuler une capture"):
                import shutil
                val_images = list(Path("dataset/val").rglob("*.png"))
                if val_images:
                    shutil.copy(val_images[np.random.randint(len(val_images))], os.path.join(camera_dir, f"sim_{int(time.time())}.png"))
                    st.rerun()

    with tab_history:
        st.subheader("Dernières détections")
        if st.session_state.history:
            df = pd.DataFrame(st.session_state.history)
            st.table(df)
        else:
            st.write("Aucun historique pour le moment.")

    with tab_stats:
        st.subheader("Analyse de performance")
        if st.session_state.history:
            df = pd.DataFrame(st.session_state.history)
            counts = df["Detection"].value_counts()
            
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Répartition des défauts**")
                st.bar_chart(counts)
            with c2:
                st.markdown("**Statistiques descriptives**")
                st.write(f"Total analysé : {len(df)}")
                st.write(f"Défaut dominant : {counts.index[0] if not counts.empty else 'N/A'}")
        else:
            st.info("Les statistiques apparaîtront après quelques détections.")

    # --- LOGIQUE AUTO-REFRESH ---
    if auto_refresh:
        placeholder = st.empty()
        for i in range(refresh_interval, 0, -1):
            placeholder.caption(f"⏳ Prochaine mise à jour dans {i}s...")
            time.sleep(1)
        st.rerun()

if __name__ == "__main__":
    main()
