"""
=============================================================
 ParticleScope — Inférence sur de nouvelles images
=============================================================
 Usage :
   python predict.py --image chemin/vers/image.png
   python predict.py --folder chemin/vers/dossier/
=============================================================
"""

import argparse
import torch
import torch.nn as nn
from torchvision import transforms, models
from PIL import Image
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

NO_DEFECT_CLASS = "sans_defaut"
WHITE_PIXEL_THRESHOLD = 1


# ── Architecture CNN from scratch ────────────────────────────
class ParticleCNN(nn.Module):
    def __init__(self, num_classes=3):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(),
            nn.Conv2d(32, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(),
            nn.MaxPool2d(2), nn.Dropout2d(0.1),
            nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(),
            nn.Conv2d(64, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(),
            nn.MaxPool2d(2), nn.Dropout2d(0.1),
            nn.Conv2d(64, 128, 3, padding=1), nn.BatchNorm2d(128), nn.ReLU(),
            nn.Conv2d(128, 128, 3, padding=1), nn.BatchNorm2d(128), nn.ReLU(),
            nn.MaxPool2d(2), nn.Dropout2d(0.2),
            nn.Conv2d(128, 256, 3, padding=1), nn.BatchNorm2d(256), nn.ReLU(),
            nn.AdaptiveAvgPool2d((4, 4)),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(256 * 4 * 4, 256), nn.ReLU(), nn.Dropout(0.4),
            nn.Linear(256, 64), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(64, num_classes),
        )

    def forward(self, x):
        return self.classifier(self.features(x))

# ── Fonction pour créer le modèle selon la config ───────────
def get_model_architecture(cfg, num_classes):
    if cfg.get("use_transfer", False):
        model = models.resnet18(weights=None) # Pas besoin de charger les poids ImageNet ici
        model.conv1 = nn.Conv2d(1, 64, 7, stride=2, padding=3, bias=False)
        model.fc = nn.Linear(model.fc.in_features, num_classes)
    else:
        model = ParticleCNN(num_classes=num_classes)
    return model

# ── Chargement du modèle ─────────────────────────────────────
def load_model(checkpoint_path: str, device: str):
    ckpt = torch.load(checkpoint_path, map_location=device)
    classes = ckpt["classes"]
    cfg = ckpt["config"]

    model = get_model_architecture(cfg, len(classes))
    model.load_state_dict(ckpt["model_state"])
    model.to(device).eval()
    return model, classes, cfg


# ── Prétraitement d'une image ────────────────────────────────
def preprocess(img_path_or_pil, img_size: int = 128):
    tf = transforms.Compose([
        transforms.Grayscale(num_output_channels=1),
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.5], std=[0.5]),
    ])
    if isinstance(img_path_or_pil, (str, Path)):
        img = Image.open(img_path_or_pil).convert("RGB")
    else:
        img = img_path_or_pil.convert("RGB")
    return tf(img).unsqueeze(0), img


def get_display_classes(classes):
    return classes if NO_DEFECT_CLASS in classes else [*classes, NO_DEFECT_CLASS]


def is_black_image(
    img,
    white_pixel_threshold=WHITE_PIXEL_THRESHOLD,
):
    gray = np.array(img.convert("L"), dtype=np.uint8)
    if gray.size == 0:
        return False

    return not np.any(gray >= white_pixel_threshold)


# ── Prédiction avec probabilités ────────────────────────────
@torch.no_grad()
def predict(model, tensor, classes, device, original_img=None):
    display_classes = get_display_classes(classes)

    if original_img is not None and is_black_image(original_img):
        probs = np.zeros(len(display_classes), dtype=np.float32)
        probs[display_classes.index(NO_DEFECT_CLASS)] = 1.0
        return NO_DEFECT_CLASS, probs, display_classes

    tensor = tensor.to(device)
    logits = model(tensor)
    probs = torch.softmax(logits, dim=1).squeeze().cpu().numpy().astype(np.float32)
    if len(display_classes) != len(classes):
        probs = np.append(probs, 0.0)
    pred_idx = probs.argmax()
    return display_classes[pred_idx], probs, display_classes


# ── Visualisation d'une image ────────────────────────────────
COLORS = {
    "tache": "#ff6b35",
    "rayure": "#00d4ff",
    "inclusion": "#7b61ff",
    NO_DEFECT_CLASS: "#10b981",
}

def show_result(img, img_name, pred_class, probs, classes):
    fig, (ax_img, ax_bar) = plt.subplots(1, 2, figsize=(10, 4))
    fig.patch.set_facecolor('#060a0f')

    # Image originale
    ax_img.imshow(img, cmap='gray')
    ax_img.set_title(
        f"Prédit : {pred_class.upper()}  ({probs.max():.0%})",
        color=COLORS.get(pred_class, 'white'), fontsize=13, fontweight='bold'
    )
    ax_img.axis('off')
    ax_img.set_facecolor('#000')

    # Barres de probabilité
    bar_colors = [COLORS.get(c, '#888') for c in classes]
    bars = ax_bar.barh(classes, probs * 100, color=bar_colors, height=0.5)
    ax_bar.set_xlim(0, 100)
    ax_bar.set_xlabel("Probabilité (%)", color='#c8dae8')
    ax_bar.set_title("Distribution des classes", color='white')
    ax_bar.set_facecolor('#0c1219')
    ax_bar.tick_params(colors='#c8dae8')
    ax_bar.spines[:].set_color('#1a2d42')

    for bar, prob in zip(bars, probs):
        ax_bar.text(bar.get_width() + 1, bar.get_y() + bar.get_height() / 2,
                    f"{prob:.1%}", va='center', color='white', fontsize=10)

    plt.suptitle(img_name, color='#4a6070', fontsize=9)
    plt.tight_layout()
    plt.show()


# ── Traitement d'un dossier ──────────────────────────────────
def predict_folder(model, folder_path, classes, cfg, device):
    exts = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'}
    images = [p for p in Path(folder_path).iterdir() if p.suffix.lower() in exts]

    if not images:
        print("Aucune image trouvée dans ce dossier.")
        return

    print(f"\n{'Image':<30} {'Classe':>10}  {'Confiance':>10}")
    print("─" * 55)
    for img_path in sorted(images):
        tensor, img = preprocess(str(img_path), cfg.get("img_size", 128))
        pred, probs, _ = predict(model, tensor, classes, device, original_img=img)
        conf = probs.max()
        flag = "⚠️" if conf < 0.6 else ""
        print(f"{img_path.name:<30} {pred:>10}  {conf:>9.1%}  {flag}")


# ── CLI ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="ParticleScope — Inférence")
    parser.add_argument("--model",   default="outputs/best_model.pth", help="Chemin du checkpoint")
    parser.add_argument("--image",   default=None, help="Image à classifier")
    parser.add_argument("--folder",  default=None, help="Dossier d'images à classifier")
    parser.add_argument("--no-plot", action="store_true", help="Désactiver la visualisation")
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    if not Path(args.model).exists():
        print(f"Erreur : Le modèle {args.model} n'existe pas. Lancez d'abord train.py.")
        return

    model, classes, cfg = load_model(args.model, device)
    print(f"✓ Modèle chargé  |  Classes : {classes}  |  Device : {device}")

    if args.image:
        tensor, img = preprocess(args.image, cfg.get("img_size", 128))
        pred, probs, display_classes = predict(model, tensor, classes, device, original_img=img)
        print(f"\n→ Résultat : {pred.upper()}  (confiance : {probs.max():.1%})")
        for cls, p in zip(display_classes, probs):
            print(f"   {cls:<12} {p:.1%}")
        if not args.no_plot:
            show_result(img, Path(args.image).name, pred, probs, display_classes)

    elif args.folder:
        predict_folder(model, args.folder, classes, cfg, device)

    else:
        print("Spécifiez --image ou --folder")


if __name__ == "__main__":
    main()
