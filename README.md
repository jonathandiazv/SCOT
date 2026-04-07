# SCOT : Système de Contrôle Optique Transparent

SCOT est une solution de vision industrielle basée sur le Deep Learning (PyTorch) conçue pour identifier et classifier automatiquement trois types de défauts sur des surfaces : Inclusions, Rayures et Taches.

---

## Architecture du Projet

Le projet est structuré de manière modulaire pour faciliter l'entraînement, l'évaluation et le déploiement en temps réel.

- **`train.py`** : Pipeline complet d'entraînement (Data Augmentation, Transfer Learning avec ResNet18 ou CNN custom, gestion du déséquilibre des classes).
- **`predict.py`** : Script d'inférence polyvalent pour analyser une image unique ou un dossier complet.
- **`app.py`** : Interface utilisateur interactive (Streamlit) pour le monitoring en temps réel d'un flux d'images (caméra).
- **`dataset/`** : Répertoire de données organisé par classes (`train/` et `val/`).
- **`outputs/`** : Stockage automatique des modèles entraînés (`.pth`), matrices de confusion et courbes d'apprentissage.

---

## Installation & Configuration

### 1. Prérequis
- Python 3.9+
- CUDA (optionnel, pour accélération GPU)

### 2. Installation des dépendances
```bash
pip install -r requirements.txt
```

---

## Utilisation

### Étape 1 : Entraînement
```bash
python train.py
```

### Étape 2 : Inférence (Test)
```bash
python predict.py --image "chemin/vers/votre_image.png"
```

### Étape 3 : Application Temps Réel (SCOT Dashboard)
```bash
python -m streamlit run app.py
```

---
*Développé dans le cadre du Projet Innovation SCOT.*
