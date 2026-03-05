"""
=============================================================
 ParticleScope — Entraînement du classificateur de traces
=============================================================
 Classes : tache | rayure | inclusion
 Modèle  : CNN léger (from scratch) + option Transfer Learning
 Input   : images N&B (fond noir, trace blanche)
=============================================================
"""

# ── Bibliothèques standard Python ──
import os                          # gestion des chemins et dossiers
import numpy as np                 # calculs numériques (tableaux, stats)
import matplotlib.pyplot as plt    # création de graphiques
from pathlib import Path           # manipulation de chemins de fichiers

# ── PyTorch : framework de deep learning ──
import torch                               # tenseurs et calcul GPU
import torch.nn as nn                      # couches de réseaux de neurones
import torch.optim as optim                # algorithmes d'optimisation (AdamW, SGD…)
from torch.utils.data import DataLoader, WeightedRandomSampler
# DataLoader            : itérateur qui fournit les images par lots (batches) au modèle
# WeightedRandomSampler : tire les exemples avec des probabilités ajustées
#                         pour compenser les classes sous-représentées

# ── TorchVision : outils pour la vision par ordinateur ──
from torchvision import datasets, transforms, models
# datasets.ImageFolder : charge automatiquement les images depuis un dossier organisé par classe
# transforms           : pipeline de transformations (redimensionnement, normalisation, augmentation…)
# models               : modèles pré-entraînés (ResNet, VGG…) pour le transfer learning

# ── Métriques d'évaluation ──
from sklearn.metrics import classification_report, confusion_matrix
# classification_report : précision, rappel, F1-score par classe
# confusion_matrix      : tableau montrant les erreurs de classification entre classes
import seaborn as sns              # visualisation de la matrice de confusion en heatmap


# ─────────────────────────────────────────────
#  CONFIGURATION — modifiez ces valeurs
# ─────────────────────────────────────────────
CONFIG = {
    "data_dir":     "dataset/",     # chemin vers le dossier contenant train/ et val/
    "output_dir":   "outputs/",  # où sauvegarder le modèle et les graphiques
    "img_size":     128,         # toutes les images seront redimensionnées en 128×128 px
    "batch_size":   32,          # nombre d'images traitées simultanément à chaque étape
    "epochs":       30,          # nombre de passages complets sur le dataset d'entraînement
    "lr":           1e-3,        # learning rate : vitesse d'apprentissage (0.001)
    "weight_decay": 1e-4,        # régularisation L2 : pénalise les grands poids pour éviter le surapprentissage
    "use_transfer": False,       # False = CNN from scratch | True = ResNet18 pré-entraîné
    "classes":      ["tache", "rayure", "inclusion"],
    "device":       "cuda" if torch.cuda.is_available() else "cpu",
    # "cuda" = GPU Nvidia (entraînement rapide) | "cpu" = processeur (plus lent)
}

# ─────────────────────────────────────────────
#  STRUCTURE DE DOSSIERS ATTENDUE
# ─────────────────────────────────────────────
# data/
# ├── train/
# │   ├── tache/        ← vos images de taches
# │   ├── rayure/       ← vos images de rayures
# │   └── inclusion/    ← vos images d'inclusions
# └── val/
#     ├── tache/
#     ├── rayure/
#     └── inclusion/


# ─────────────────────────────────────────────
#  AUGMENTATION & NORMALISATION
# ─────────────────────────────────────────────
def get_transforms(img_size: int):
    """
    Retourne deux pipelines de transformations :
    - train_transform : avec augmentation (crée artificiellement de la variété)
    - val_transform   : sans augmentation (on évalue sur les images telles quelles)

    L'augmentation simule différentes conditions d'acquisition :
    orientation variable, léger décalage, variations d'intensité.
    """

    # ── Transformations pour l'entraînement (avec augmentation) ──
    train_tf = transforms.Compose([
        # Convertit en niveaux de gris (1 canal) — nos images sont déjà N&B
        # mais certaines peuvent être sauvegardées en RGB par erreur
        transforms.Grayscale(num_output_channels=1),

        # Redimensionne toutes les images à img_size × img_size pixels
        # Nécessaire pour que le réseau reçoive toujours la même taille en entrée
        transforms.Resize((img_size, img_size)),

        # Retourne l'image horizontalement avec une probabilité de 50%
        # Une trace peut apparaître dans n'importe quelle direction
        transforms.RandomHorizontalFlip(),

        # Retourne l'image verticalement avec une probabilité de 50%
        transforms.RandomVerticalFlip(),

        # Rotation aléatoire jusqu'à ±180° — les traces de particules
        # n'ont pas d'orientation privilégiée (isotropie)
        transforms.RandomRotation(180),

        # Décalage aléatoire de la trace dans l'image (max 10% de la taille)
        # Evite que le modèle apprenne la position plutôt que la forme
        transforms.RandomAffine(0, translate=(0.1, 0.1)),

        # Variation légère de luminosité et de contraste (±20%)
        # Simule des conditions d'acquisition différentes
        transforms.ColorJitter(brightness=0.2, contrast=0.2),

        # Convertit l'image PIL en tenseur PyTorch et normalise les pixels dans [0, 1]
        transforms.ToTensor(),

        # Recentre les valeurs de pixels autour de 0 : [0,1] → [-1, 1]
        # pixel_normalisé = (pixel - 0.5) / 0.5
        # Aide le réseau à converger plus vite
        transforms.Normalize(mean=[0.5], std=[0.5]),
    ])

    # ── Transformations pour la validation (sans augmentation) ──
    # On évalue le modèle sur les images originales pour mesurer
    # ses vraies performances, sans modifications artificielles
    val_tf = transforms.Compose([
        transforms.Grayscale(num_output_channels=1),
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.5], std=[0.5]),
    ])

    return train_tf, val_tf


# ─────────────────────────────────────────────
#  CHARGEMENT DES DONNÉES
# ─────────────────────────────────────────────
def load_datasets(cfg: dict):
    """
    Charge les images depuis les dossiers data/train/ et data/val/,
    applique les transformations, et retourne des DataLoaders
    prêts à être utilisés dans la boucle d'entraînement.
    """
    # Récupère les deux pipelines de transformations
    train_tf, val_tf = get_transforms(cfg["img_size"])

    # ImageFolder parcourt automatiquement les sous-dossiers et associe
    # chaque image à un label selon le nom du dossier parent
    # ex : data/train/tache/img001.png → label "tache" → index 0
    train_ds = datasets.ImageFolder(
        root=os.path.join(cfg["data_dir"], "train"),
        transform=train_tf
    )
    val_ds = datasets.ImageFolder(
        root=os.path.join(cfg["data_dir"], "val"),
        transform=val_tf
    )

    # ── Gestion des classes déséquilibrées ──
    # Problème : si on a 200 taches, 50 rayures et 80 inclusions,
    # le modèle va apprendre à prédire "tache" trop souvent.
    # Solution : on tire plus souvent les classes rares lors de l'entraînement.

    # Compte combien d'images on a par classe : ex [200, 50, 80]
    class_counts = np.bincount(train_ds.targets)

    # Poids inversement proportionnels au nombre d'exemples :
    # classe rare → poids élevé → tirée plus souvent
    weights = 1.0 / class_counts

    # Associe un poids à chaque image individuelle selon sa classe
    sample_weights = weights[train_ds.targets]

    # Sampler qui respecte ces poids lors du tirage aléatoire des batches
    sampler = WeightedRandomSampler(sample_weights, len(sample_weights))

    # ── DataLoaders : fournissent les images par lots au modèle ──
    train_loader = DataLoader(
        train_ds,
        batch_size=cfg["batch_size"],  # taille d'un lot (ex : 32 images à la fois)
        sampler=sampler,               # tirage pondéré (remplace shuffle=True)
        num_workers=2,                 # 2 processus parallèles pour charger les images
        pin_memory=True                # pré-charge en RAM pour accélérer le transfert GPU
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=cfg["batch_size"],
        shuffle=False,                 # pas besoin de mélanger en validation
        num_workers=2,
        pin_memory=True
    )

    # Affiche un résumé du dataset chargé
    print(f"✓ Train : {len(train_ds)} images  |  Val : {len(val_ds)} images")
    print(f"  Classes détectées : {train_ds.classes}")
    print(f"  Distribution train : {dict(zip(train_ds.classes, class_counts))}")

    return train_loader, val_loader, train_ds.classes


# ─────────────────────────────────────────────
#  ARCHITECTURE DU RÉSEAU DE NEURONES (CNN)
# ─────────────────────────────────────────────
class ParticleCNN(nn.Module):
    """
    Réseau de neurones convolutif (CNN) conçu pour classifier
    des images N&B de traces de particules.

    Architecture en deux parties :
    1. features    : extrait les caractéristiques visuelles (formes, textures)
    2. classifier  : prend ces caractéristiques et prédit la classe

    Principe d'un bloc convolutif :
      Conv2d → BatchNorm → ReLU → Conv2d → BatchNorm → ReLU → MaxPool → Dropout
    Chaque bloc double le nombre de filtres et réduit la taille spatiale de moitié.
    """

    def __init__(self, num_classes: int = 3):
        super().__init__()

        # ── Partie extraction de caractéristiques ──
        self.features = nn.Sequential(

            # ── Bloc 1 : détecte les contours et textures simples ──
            # Conv2d(in_channels, out_channels, kernel_size, padding)
            # 1 canal en entrée (N&B), 32 filtres de 3×3
            # padding=1 : conserve la taille spatiale après convolution
            nn.Conv2d(1, 32, 3, padding=1),
            nn.BatchNorm2d(32),   # normalise les activations → entraînement plus stable
            nn.ReLU(),            # activation non-linéaire : remplace les valeurs négatives par 0
            nn.Conv2d(32, 32, 3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d(2),      # divise la résolution par 2 (128×128 → 64×64)
            nn.Dropout2d(0.1),    # éteint aléatoirement 10% des canaux → évite le surapprentissage

            # ── Bloc 2 : détecte des formes plus complexes ──
            # 32 canaux en entrée, 64 en sortie (le réseau "voit" plus de motifs)
            nn.Conv2d(32, 64, 3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.Conv2d(64, 64, 3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.MaxPool2d(2),      # 64×64 → 32×32
            nn.Dropout2d(0.1),

            # ── Bloc 3 : détecte des structures de haut niveau ──
            nn.Conv2d(64, 128, 3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(),
            nn.Conv2d(128, 128, 3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(),
            nn.MaxPool2d(2),      # 32×32 → 16×16
            nn.Dropout2d(0.2),    # dropout plus fort car représentation plus abstraite

            # ── Bloc 4 : représentation finale très compacte ──
            nn.Conv2d(128, 256, 3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(),
            # AdaptiveAvgPool2d : force la sortie à être exactement 4×4,
            # quelle que soit la taille d'entrée — rend le réseau flexible
            nn.AdaptiveAvgPool2d((4, 4)),
        )
        # À ce stade, chaque image est représentée par un tenseur 256 × 4 × 4

        # ── Partie classification ──
        self.classifier = nn.Sequential(
            # Flatten : aplatit le tenseur 3D (256×4×4) en vecteur 1D (4096 valeurs)
            nn.Flatten(),

            # Couche dense : 4096 → 256 neurones
            nn.Linear(256 * 4 * 4, 256),
            nn.ReLU(),
            nn.Dropout(0.4),   # 40% des neurones éteints aléatoirement

            # Couche dense : 256 → 64 neurones
            nn.Linear(256, 64),
            nn.ReLU(),
            nn.Dropout(0.3),

            # Couche de sortie : 64 → num_classes (3) scores bruts (logits)
            # Pas de softmax ici : CrossEntropyLoss l'applique en interne
            nn.Linear(64, num_classes),
        )

    def forward(self, x):
        """
        Passage avant (forward pass) : définit comment une image x
        traverse le réseau pour produire des scores de classification.
        x : tenseur de forme [batch_size, 1, img_size, img_size]
        """
        return self.classifier(self.features(x))


def get_model(cfg: dict, num_classes: int) -> nn.Module:
    """
    Instancie et retourne le modèle selon la configuration.
    Deux options :
    - ParticleCNN from scratch (par défaut)
    - ResNet18 pré-entraîné sur ImageNet (transfer learning)
    """
    if cfg["use_transfer"]:
        # Charge ResNet18 avec ses poids pré-entraînés sur 1.2M d'images ImageNet
        model = models.resnet18(weights="IMAGENET1K_V1")

        # ResNet attend 3 canaux (RGB) en entrée — on remplace la 1ère couche
        # pour accepter 1 canal (N&B) en conservant les autres poids intacts
        model.conv1 = nn.Conv2d(1, 64, 7, stride=2, padding=3, bias=False)

        # Remplace la dernière couche pour prédire nos 3 classes
        # (ResNet de base prédit 1000 classes ImageNet)
        model.fc = nn.Linear(model.fc.in_features, num_classes)
        print("✓ Modèle : ResNet18 (transfer learning)")
    else:
        model = ParticleCNN(num_classes)
        print("✓ Modèle : ParticleCNN (from scratch)")

    # Affiche le nombre total de paramètres apprenables
    total = sum(p.numel() for p in model.parameters())
    print(f"  Paramètres : {total:,}")

    # Envoie le modèle sur GPU ou CPU selon la config
    return model.to(cfg["device"])


# ─────────────────────────────────────────────
#  BOUCLE D'ENTRAÎNEMENT
# ─────────────────────────────────────────────
def train_one_epoch(model, loader, optimizer, criterion, device):
    """
    Effectue un passage complet sur le dataset d'entraînement (1 époque).
    Pour chaque batch d'images :
      1. Calcule la prédiction du modèle (forward pass)
      2. Mesure l'erreur (loss)
      3. Calcule les gradients (backward pass)
      4. Met à jour les poids (optimizer step)

    Retourne la loss moyenne et la précision sur toute l'époque.
    """
    model.train()  # active les couches spécifiques à l'entraînement (BatchNorm, Dropout)

    total_loss, correct, total = 0, 0, 0

    for imgs, labels in loader:
        # Transfère les données sur GPU si disponible
        imgs, labels = imgs.to(device), labels.to(device)

        # Réinitialise les gradients accumulés au batch précédent
        # (PyTorch accumule les gradients par défaut — il faut les remettre à 0)
        optimizer.zero_grad()

        # Forward pass : le modèle prédit les scores pour chaque classe
        # out : tenseur de forme [batch_size, num_classes]
        out = model(imgs)

        # Calcule la Cross-Entropy Loss entre prédictions et vraies étiquettes
        # Cette loss est élevée si le modèle se trompe, faible s'il a raison
        loss = criterion(out, labels)

        # Backward pass : calcule le gradient de la loss par rapport
        # à chaque paramètre du réseau (rétropropagation)
        loss.backward()

        # Met à jour les poids selon les gradients calculés
        optimizer.step()

        # Accumule les statistiques du batch
        total_loss += loss.item() * imgs.size(0)  # loss totale (dépilée du GPU)
        correct += (out.argmax(1) == labels).sum().item()  # nb de bonnes prédictions
        total += imgs.size(0)                              # nb total d'images vues

    # Retourne loss et accuracy moyennes sur toute l'époque
    return total_loss / total, correct / total


@torch.no_grad()  # désactive le calcul des gradients → plus rapide et moins de mémoire
def evaluate(model, loader, criterion, device):
    """
    Évalue le modèle sur le dataset de validation.
    Pas de mise à jour des poids — on mesure seulement les performances.
    Retourne : loss, accuracy, toutes les prédictions, toutes les vraies étiquettes.
    """
    model.eval()  # désactive Dropout et met BatchNorm en mode évaluation

    total_loss, correct, total = 0, 0, 0
    all_preds, all_labels = [], []  # pour construire le rapport de classification

    for imgs, labels in loader:
        imgs, labels = imgs.to(device), labels.to(device)

        out = model(imgs)
        loss = criterion(out, labels)

        total_loss += loss.item() * imgs.size(0)

        # argmax(1) : prend l'indice de la classe avec le score le plus élevé
        preds = out.argmax(1)
        correct += (preds == labels).sum().item()
        total += imgs.size(0)

        # Collecte les prédictions et labels pour les métriques finales
        # .cpu() : ramène les tenseurs du GPU vers la RAM
        # .numpy() : convertit en tableau NumPy pour scikit-learn
        all_preds.extend(preds.cpu().numpy())
        all_labels.extend(labels.cpu().numpy())

    return total_loss / total, correct / total, all_preds, all_labels


# ─────────────────────────────────────────────
#  VISUALISATIONS
# ─────────────────────────────────────────────
def plot_history(history: dict, out_dir: str):
    """
    Trace et sauvegarde les courbes d'entraînement :
    - Loss train vs val : détecte le surapprentissage (val loss qui remonte)
    - Accuracy train vs val : mesure la progression de l'apprentissage
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

    # Style sombre cohérent avec l'interface
    fig.patch.set_facecolor('#060a0f')
    for ax in [ax1, ax2]:
        ax.set_facecolor('#0c1219')
        ax.tick_params(colors='#c8dae8')
        ax.spines[:].set_color('#1a2d42')

    # Courbe de loss : doit diminuer pour les deux courbes
    ax1.plot(history['train_loss'], color='#00d4ff', label='Train')
    ax1.plot(history['val_loss'],   color='#ff6b35', label='Val')
    ax1.set_title('Loss', color='white')
    ax1.legend()

    # Courbe d'accuracy : doit augmenter pour les deux courbes
    ax2.plot(history['train_acc'], color='#00d4ff', label='Train')
    ax2.plot(history['val_acc'],   color='#ff6b35', label='Val')
    ax2.set_title('Accuracy', color='white')
    ax2.legend()

    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "training_history.png"), dpi=150, bbox_inches='tight')
    plt.close()
    print("✓ Courbes sauvegardées : outputs/training_history.png")


def plot_confusion(preds, labels, classes, out_dir):
    """
    Trace et sauvegarde la matrice de confusion.
    Chaque cellule [i, j] indique combien d'images de la classe i
    ont été prédites comme classe j.
    La diagonale = bonnes prédictions.
    """
    cm = confusion_matrix(labels, preds)  # calcule la matrice

    fig, ax = plt.subplots(figsize=(6, 5))
    fig.patch.set_facecolor('#060a0f')
    ax.set_facecolor('#0c1219')

    # Heatmap : plus la cellule est foncée, plus la valeur est élevée
    # annot=True : affiche les chiffres dans chaque cellule
    # fmt='d' : format entier
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
                xticklabels=classes, yticklabels=classes, ax=ax)
    ax.set_title('Matrice de confusion', color='white')
    ax.tick_params(colors='#c8dae8')

    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "confusion_matrix.png"), dpi=150, bbox_inches='tight')
    plt.close()
    print("✓ Matrice de confusion : outputs/confusion_matrix.png")


# ─────────────────────────────────────────────
#  POINT D'ENTRÉE PRINCIPAL
# ─────────────────────────────────────────────
def main():
    cfg = CONFIG
    os.makedirs(cfg["output_dir"], exist_ok=True)  # crée le dossier outputs/ s'il n'existe pas
    print(f"\n🔬 ParticleScope — Entraînement")
    print(f"   Device : {cfg['device']}\n")

    # ── 1. Chargement des données ──
    train_loader, val_loader, classes = load_datasets(cfg)

    # ── 2. Création du modèle ──
    model = get_model(cfg, num_classes=len(classes))

    # ── 3. Fonction de perte, optimiseur, scheduler ──

    # CrossEntropyLoss : mesure l'écart entre les prédictions et les vraies classes
    # C'est la loss standard pour la classification multi-classes
    criterion = nn.CrossEntropyLoss()

    # AdamW : variante d'Adam avec régularisation des poids découplée
    # Plus robuste qu'Adam classique pour éviter le surapprentissage
    optimizer = optim.AdamW(
        model.parameters(),
        lr=cfg["lr"],
        weight_decay=cfg["weight_decay"]
    )

    # CosineAnnealingLR : réduit progressivement le learning rate
    # selon une courbe cosinus — évite d'osciller autour du minimum à la fin
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=cfg["epochs"])

    # ── 4. Boucle d'entraînement ──
    # Dictionnaire pour stocker les métriques à chaque époque (pour les courbes)
    history = {"train_loss": [], "val_loss": [], "train_acc": [], "val_acc": []}
    best_val_acc = 0.0
    best_model_path = os.path.join(cfg["output_dir"], "best_model.pth")

    # En-tête du tableau de suivi affiché dans le terminal
    print(f"\n{'Epoch':>6}  {'Train Loss':>10}  {'Train Acc':>9}  {'Val Loss':>8}  {'Val Acc':>7}")
    print("─" * 55)

    for epoch in range(1, cfg["epochs"] + 1):

        # Entraîne sur tout le dataset train et récupère loss + accuracy
        tr_loss, tr_acc = train_one_epoch(model, train_loader, optimizer, criterion, cfg["device"])

        # Évalue sur le dataset val (sans modifier les poids)
        vl_loss, vl_acc, preds, labels = evaluate(model, val_loader, criterion, cfg["device"])

        # Met à jour le learning rate selon le cosinus scheduler
        scheduler.step()

        # Sauvegarde les métriques pour les courbes finales
        history["train_loss"].append(tr_loss)
        history["val_loss"].append(vl_loss)
        history["train_acc"].append(tr_acc)
        history["val_acc"].append(vl_acc)

        # Affiche la ligne de résultats (★ = nouveau record de validation)
        marker = " ★" if vl_acc > best_val_acc else ""
        print(f"{epoch:>6}  {tr_loss:>10.4f}  {tr_acc:>8.1%}  {vl_loss:>8.4f}  {vl_acc:>6.1%}{marker}")

        # Sauvegarde le meilleur modèle (celui avec la meilleure val accuracy)
        # On sauvegarde aussi les classes et la config pour pouvoir faire l'inférence plus tard
        if vl_acc > best_val_acc:
            best_val_acc = vl_acc
            torch.save({
                "model_state": model.state_dict(),  # poids du réseau
                "classes":     classes,             # ["tache", "rayure", "inclusion"]
                "config":      cfg                  # paramètres d'entraînement
            }, best_model_path)

    # ── 5. Rapport final ──
    print(f"\n✓ Meilleure val accuracy : {best_val_acc:.1%}")
    print(f"✓ Modèle sauvegardé : {best_model_path}")
    print("\n── Rapport de classification ──")
    # Affiche précision, rappel et F1-score pour chaque classe
    print(classification_report(labels, preds, target_names=classes))

    # ── 6. Génération des graphiques ──
    plot_history(history, cfg["output_dir"])
    plot_confusion(preds, labels, classes, cfg["output_dir"])


# Ce bloc garantit que main() n'est appelé que si on lance ce fichier directement
# (pas si on l'importe depuis un autre script)
if __name__ == "__main__":
    main()