import streamlit as st
import torch
from PIL import Image
import os
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

# Importation des fonctions de prédiction (ou copie locale pour la robustesse)
from predict import load_model, preprocess, predict, COLORS

# Configuration de la page
st.set_page_config(
    page_title="ParticleScope - Détection de Défauts",
    page_icon="🔬",
    layout="wide"
)

# Style CSS personnalisé
st.markdown("""
    <style>
    .main {
        background-color: #060a0f;
        color: #c8dae8;
    }
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        background-color: #00d4ff;
        color: #060a0f;
        font-weight: bold;
    }
    .stAlert {
        background-color: #0c1219;
        color: #c8dae8;
        border: 1px solid #1a2d42;
    }
    h1, h2, h3 {
        color: white !important;
    }
    </style>
    """, unsafe_allow_html=True)

def main():
    st.title("🔬 ParticleScope : Analyse de Défauts")
    st.markdown("---")

    # Barre latérale pour les paramètres
    st.sidebar.header("Configuration")
    
    # ── Gestion de l'archive des modèles ──
    output_dir = "outputs"
    archive_dir = os.path.join(output_dir, "models_archive")
    default_model = os.path.join(output_dir, "best_model.pth")
    
    # Lister les modèles archivés
    archived_models = []
    if os.path.exists(archive_dir):
        archived_models = sorted(
            [f for f in os.listdir(archive_dir) if f.endswith(".pth")],
            reverse=True # Plus récent en premier
        )
    
    # Préparer les options de sélection
    model_options = []
    if os.path.exists(default_model):
        model_options.append("Dernier meilleur (best_model.pth)")
    
    model_options.extend([os.path.join("models_archive", f) for f in archived_models])
    
    if not model_options:
        st.error("Aucun modèle trouvé. Veuillez lancer `train.py`.")
        return

    selected_option = st.sidebar.selectbox(
        "Choisir un modèle",
        model_options,
        index=0
    )
    
    # Construire le chemin complet
    if selected_option == "Dernier meilleur (best_model.pth)":
        model_path = default_model
    else:
        model_path = os.path.join(output_dir, selected_option)
    
    st.sidebar.write(f"📂 `{os.path.basename(model_path)}`")
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    st.sidebar.info(f"Appareil utilisé : {device}")

    # Chargement du modèle
    @st.cache_resource
    def get_cached_model(path, dev):
        if Path(path).exists():
            return load_model(path, dev)
        return None, None, None

    model, classes, cfg = get_cached_model(model_path, device)

    if model is None:
        st.error(f"⚠️ Modèle non trouvé à l'emplacement : {model_path}")
        st.info("Veuillez d'abord entraîner le modèle avec `python train.py`.")
        return

    # Zone de téléchargement d'image
    col1, col2 = st.columns([1, 1])

    with col1:
        st.header("1. Téléchargement")
        uploaded_file = st.file_uploader("Choisissez une image de trace...", type=["png", "jpg", "jpeg", "bmp", "tif"])
        
        if uploaded_file is not None:
            image = Image.open(uploaded_file)
            st.image(image, caption="Image originale", use_container_width=True)

    with col2:
        st.header("2. Diagnostic")
        if uploaded_file is not None:
            if st.button("Lancer l'Analyse"):
                with st.spinner('Analyse en cours...'):
                    # Prétraitement et prédiction
                    tensor, img_pil = preprocess(image, cfg.get("img_size", 128))
                    pred_class, probs = predict(model, tensor, classes, device)
                    
                    # Affichage du résultat principal
                    confiance = probs.max()
                    couleur = COLORS.get(pred_class, "#ffffff")
                    
                    st.markdown(f"""
                        <div style="padding: 20px; border-radius: 10px; background-color: #0c1219; border-left: 10px solid {couleur};">
                            <h2 style="margin: 0;">Résultat : <span style="color: {couleur};">{pred_class.upper()}</span></h2>
                            <p style="font-size: 20px; margin: 10px 0 0 0;">Confiance : <b>{confiance:.1%}</b></p>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # Graphique des probabilités
                    st.markdown("### Distribution des probabilités")
                    fig, ax = plt.subplots(figsize=(10, 4))
                    fig.patch.set_facecolor('#060a0f')
                    ax.set_facecolor('#0c1219')
                    
                    bar_colors = [COLORS.get(c, '#888') for c in classes]
                    bars = ax.barh(classes, probs * 100, color=bar_colors)
                    ax.set_xlim(0, 100)
                    ax.set_xlabel("Probabilité (%)", color='#c8dae8')
                    ax.tick_params(colors='#c8dae8')
                    ax.spines[:].set_color('#1a2d42')
                    
                    for bar, prob in zip(bars, probs):
                        ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2, 
                                f'{prob:.1%}', va='center', color='white')
                    
                    st.pyplot(fig)
                    
                    if confiance < 0.6:
                        st.warning("⚠️ La confiance est faible. Le défaut pourrait être ambigu ou d'une classe inconnue.")
        else:
            st.info("Veuillez télécharger une image pour commencer l'analyse.")

    # Section d'aide / Explication des classes
    with st.expander("ℹ️ Informations sur les types de défauts"):
        st.markdown("""
        *   **Inclusion** : Corps étranger emprisonné dans la matière. Souvent de forme irrégulière.
        *   **Rayure** : Trace linéaire causée par un frottement. Longue et étroite.
        *   **Tache** : Zone de décoloration ou résidu en surface. Souvent circulaire ou diffuse.
        """)

if __name__ == "__main__":
    main()
