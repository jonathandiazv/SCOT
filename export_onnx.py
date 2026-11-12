"""
=============================================================
 SCOT — Export d'un checkpoint PyTorch (.pth) vers ONNX
=============================================================
 Le modèle est entraîné en local (train.py), puis exporté en ONNX
 pour l'inférence sur Azure (Function) : onnxruntime est ~15 Mo,
 contre plusieurs centaines de Mo pour PyTorch.

 Les classes et la taille d'image sont embarquées dans les
 métadonnées du fichier .onnx : la Function n'a besoin de rien d'autre.

 Usage :
   python export_onnx.py                                   # outputs/best_model.pth
   python export_onnx.py --model outputs/models_archive/MODEL_8562_202605022043.pth
   python export_onnx.py --check test_images/defects        # compare PyTorch vs ONNX
=============================================================
"""

import argparse
import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch

from predict import load_model, preprocess

IMG_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


def export(pth_path: Path, onnx_path: Path) -> dict:
    model, classes, cfg = load_model(str(pth_path), "cpu")
    img_size = cfg.get("img_size", 128)
    dummy = torch.zeros(1, 1, img_size, img_size)

    torch.onnx.export(
        model, (dummy,), str(onnx_path),
        input_names=["image"], output_names=["logits"],
        opset_version=18, dynamo=True, external_data=False,
    )

    # Métadonnées lues par la Function et l'app
    ckpt = torch.load(str(pth_path), map_location="cpu")
    meta = {
        "classes": json.dumps(list(classes)),
        "img_size": str(img_size),
        "source_checkpoint": pth_path.name,
        "score": str(ckpt.get("score", "")),
        "metrics": json.dumps(ckpt.get("metrics", {})),
        "timestamp": str(ckpt.get("timestamp", "")),
    }
    m = onnx.load(str(onnx_path))
    del m.metadata_props[:]
    for k, v in meta.items():
        m.metadata_props.add(key=k, value=v)
    onnx.checker.check_model(m)
    onnx.save(m, str(onnx_path))
    return {"model": model, "classes": classes, "img_size": img_size}


def check(onnx_path: Path, model, img_size: int, folder: Path) -> float:
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    images = sorted(p for p in folder.rglob("*") if p.suffix.lower() in IMG_EXTS)
    max_diff = 0.0
    for p in images:
        tensor, _ = preprocess(str(p), img_size)
        with torch.no_grad():
            ref = torch.softmax(model(tensor), 1).numpy()
        logits = sess.run(None, {"image": tensor.numpy()})[0]
        out = np.exp(logits - logits.max(1, keepdims=True))
        out /= out.sum(1, keepdims=True)
        diff = float(np.abs(ref - out).max())
        max_diff = max(max_diff, diff)
        same = "OK " if ref.argmax() == out.argmax() else "DIFF"
        print(f"  {same} {p.name:<25} écart max proba = {diff:.2e}")
    return max_diff


def main():
    ap = argparse.ArgumentParser(description="Export .pth → .onnx")
    ap.add_argument("--model", default="outputs/best_model.pth")
    ap.add_argument("--out", default=None, help="Chemin .onnx (défaut : même nom que le .pth)")
    ap.add_argument("--check", default="test_images", help="Dossier d'images pour comparer PyTorch et ONNX")
    args = ap.parse_args()

    pth = Path(args.model)
    out = Path(args.out) if args.out else pth.with_suffix(".onnx")
    res = export(pth, out)
    print(f"✓ Export : {out}  ({out.stat().st_size / 1e6:.1f} Mo)  classes={res['classes']}")

    if args.check and Path(args.check).exists():
        print(f"\nComparaison PyTorch / ONNX sur {args.check} :")
        diff = check(out, res["model"], res["img_size"], Path(args.check))
        print(f"\n{'✓' if diff < 1e-4 else '⚠'} Écart maximal : {diff:.2e}")


if __name__ == "__main__":
    main()
