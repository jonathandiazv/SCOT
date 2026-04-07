# SCOT : Système de Contrôle Optique des Traces

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

### 3. Structure du Dataset
Organisez vos images comme suit :
```text
dataset/
├── train/
│   ├── inclusion/
│   ├── rayure/
│   └── tache/
└── val/
    ├── inclusion/
    ├── rayure/
    └── tache/
```

---

## Utilisation

### Étape 1 : Entraînement
Pour lancer l'entraînement du modèle (par défaut utilise ResNet18 pour une précision maximale) :
```bash
python train.py
```
*Le script générera un fichier `best_model.pth` dans le dossier `outputs/`.*

### Étape 2 : Inférence (Test)
Pour tester le modèle sur une image spécifique :
```bash
python predict.py --image "chemin/vers/votre_image.png"
```
Ou sur un dossier complet :
```bash
python predict.py --folder "data_camera/"
```

### Étape 3 : Application Temps Réel (SCOT Dashboard)
Pour lancer l'interface de monitoring interactive :
```bash
python -m streamlit run app.py
```

---

## Interface SCOT Dashboard

L'application offre les fonctionnalités suivantes :
- **Monitoring Auto-Refresh** : Surveille le dossier `data_camera/` et analyse automatiquement chaque nouvelle capture.
- **Archive des Modèles** : Permet de basculer instantanément entre différentes versions de modèles entraînés.
- **Diagnostic Détaillé** : Affiche les probabilités par classe et un indicateur visuel de confiance.
- **Statistiques** : Analyse de la répartition des défauts détectés sur la session en cours.

---

## Performances & Métriques
Après chaque entraînement, consultez le dossier `outputs/` pour :
- `training_history.png` : Analyse de la convergence (Loss/Accuracy).
- `confusion_matrix.png` : Analyse détaillée des erreurs par classe.

---
*Développé dans le cadre du Projet Innovation SCOT.*
