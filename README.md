# 🔬 ParticleScope — Classificateur de Traces de Particules

## Structure du projet
```
particle_classifier/
├── train.py          ← Entraînement du modèle
├── predict.py        ← Inférence sur nouvelles images
├── requirements.txt
└── data/
    ├── train/
    │   ├── tache/
    │   ├── rayure/
    │   └── inclusion/
    └── val/
        ├── tache/
        ├── rayure/
        └── inclusion/
```

## Installation
```bash
pip install -r requirements.txt
```

## Préparer vos données
Placez vos images dans `data/train/` et `data/val/` selon la structure ci-dessus.
**Conseil :** visez 80% train / 20% val, avec au minimum ~50 images par classe.

## Entraîner le modèle
```bash
python train.py
```
Modifiez le bloc `CONFIG` dans `train.py` pour ajuster les hyperparamètres.

### Options clés dans CONFIG
| Paramètre | Défaut | Description |
|---|---|---|
| `img_size` | 128 | Taille de redimensionnement |
| `epochs` | 30 | Nombre d'époques |
| `lr` | 1e-3 | Taux d'apprentissage |
| `use_transfer` | False | Activer ResNet18 pré-entraîné |

## Inférence
```bash
# Une seule image
python predict.py --image ma_trace.png

# Tout un dossier
python predict.py --folder nouveaux_echantillons/

# Sans affichage graphique
python predict.py --image ma_trace.png --no-plot
```

## Résultats générés après entraînement
- `outputs/best_model.pth` — meilleur modèle sauvegardé
- `outputs/training_history.png` — courbes loss / accuracy
- `outputs/confusion_matrix.png` — matrice de confusion
