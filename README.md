# SCOT : Système de Contrôle Optique Transparent / Transparent Optical Control System

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![PyTorch](https://img.shields.io/badge/PyTorch-%23EE4C2C.svg?style=flat&logo=PyTorch&logoColor=white)](https://pytorch.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-%23FF4B4B.svg?style=flat&logo=Streamlit&logoColor=white)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An advanced industrial computer vision solution powered by Deep Learning to automate quality control on transparent surfaces.

---

## Table of Contents
1. [Functional Context (English)](#1-functional-context-english)
2. [Contexte Fonctionnel (Français)](#2-contexte-fonctionnel-français)
3. [Repository Structure](#3-repository-structure)
4. [Technical Architecture & Features](#4-technical-architecture--features)
5. [Installation & Setup](#5-installation--setup)
6. [Usage Guide](#6-usage-guide)
7. [Advanced Optimization (CCCC Score)](#7-advanced-optimization-cccc-score)
8. [License & Acknowledgments](#8-license--acknowledgments)

---

## 1. Functional Context (English)

### Industrial Vision for Optical Inspection
**SCOT (Transparent Optical Control System)** is an enterprise-grade artificial intelligence solution designed for high-precision manufacturing and industrial quality assurance. In modern production lines, manual visual inspection of transparent or highly reflective surfaces (such as glass panels, plastic lenses, optical filters, or polymers) is physically exhausting, highly subjective, and a major bottleneck.

SCOT automates this critical task by integrating state-of-the-art Deep Learning models directly into the production workflow. It analyzes high-speed camera feeds to detect, classify, and log surface defects instantly. This ensures 100% compliance with strict industrial standards while reducing operational costs and material waste.

### Classified Defects
SCOT is currently trained to detect and categorize the following conditions:

*   **Inclusions (`inclusion`):** Internal material impurities, bubbles, or foreign bodies embedded within the transparent medium during synthesis or cooling. These pose severe structural integrity and aesthetic risks.
*   **Scratches (`rayure`):** Linear physical abrasions on the surface caused by mechanical handling or friction.
*   **Spots (`tache`):** Superficial chemical residues, grease, fingerprints, or dust deposits that compromise transparency.
*   **No Defect (`sans_defaut`):** Compliant, perfectly clear surfaces meeting all optical tolerance requirements.

---

## 2. Contexte Fonctionnel (Français)

### Vision Industrielle pour le Contrôle Optique
**SCOT (Système de Contrôle Optique Transparent)** est une solution d'intelligence artificielle de niveau industriel dédiée à la manufacture de haute précision et au contrôle qualité automatique. Sur les lignes de production modernes, l'inspection visuelle manuelle de surfaces transparentes ou hautement réfléchissantes (comme le verre, les lentilles plastiques, les filtres optiques ou les polymères) est fastidieuse, sujette à la fatigue humaine, hautement subjective et constitue un goulot d'étranglement majeur.

SCOT automatise cette étape critique en intégrant des modèles avancés de Deep Learning directement dans le flux opérationnel. Il analyse les flux de caméras d'inspection pour détecter, classifier et journaliser instantanément les anomalies de surface. Cela garantit une conformité totale avec les cahiers des charges industriels tout en réduisant considérablement les rebuts et les coûts d'exploitation.

### Défauts Classifiés
Le système est actuellement calibré pour classifier les états suivants :

*   **Inclusions (`inclusion`) :** Impuretés physiques ou bulles d'air emprisonnées à l'intérieur de la matière transparente lors de la phase de fabrication ou de refroidissement. Elles représentent un risque de fragilité structurelle majeur.
*   **Rayures (`rayure`) :** Abrasions linéaires de surface issues de frottements ou de manipulations mécaniques.
*   **Taches (`tache`) :** Dépôts superficiels de graisse, résidus chimiques, empreintes ou poussières altérant la transparence.
*   **Sans Défaut (`sans_defaut`) :** Surfaces conformes, exemptes de toute anomalie optique.

---

## 3. Repository Structure

A clean, modular directory structure designed for seamless collaboration and easy integration with production environments:

```text
scot-projet-innovation/
├── app.py                     # Interactive Streamlit dashboard for real-time camera monitoring
├── predict.py                 # Multi-purpose inference engine (single-image / batch folder)
├── train.py                   # Complete training pipeline with transfer learning & validation
├── requirements.txt           # Python third-party package dependencies
├── Suivi_Version_AlgoCNN.xlsx # Spreadsheet tracking algorithm performance versions
├── README.md                  # Unified English/French technical and functional documentation
├── .gitignore                 # Excludes heavy checkpoints, local datasets, and virtual environments
│
├── dataset/                   # Training & Validation dataset (locally reconstructed; git-ignored)
│   ├── train/                 # 80% Training partition
│   │   ├── inclusion/
│   │   ├── rayure/
│   │   └── tache/
│   └── val/                   # 20% Validation partition
│       ├── inclusion/
│       ├── rayure/
│       └── tache/
│
├── test_images/               # Certified sample images for instant verification and CLI demos
│   ├── defects/               # Images containing certified surface defects
│   └── no_defects/            # Compliant surface images (no defect detected)
│
├── data_camera/               # Simulated directory for active real-time camera image acquisition
│   ├── img_test.png
│   └── img_test3.png
│
└── outputs/                   # Direct evaluation metrics & model weights (git-ignored)
    ├── best_model.pth         # Optimal serialized model dictionary based on CCCC optimization
    ├── confusion_matrix.png   # Performance matrix representing class-wise distribution errors
    ├── training_history.png   # Training vs validation loss & accuracy convergence curves
    └── models_archive/        # Archive of historically superior checkpoints versioned by performance
```

---

## 4. Technical Architecture & Features

### Core Capabilities
*   **Model Flexibility:** Supports training from scratch using a custom, high-efficiency CNN (`ParticleCNN`) or utilizing **Transfer Learning** on a pre-trained **ResNet18** model with a adapted grayscale input layer.
*   **Data Augmentation Suite:** High-performance pre-processing and pipeline augmentation designed specifically for optical textures, including:
    *   Random Horizontal & Vertical Flips (Isotropy)
    *   Random Rotations (up to 180°)
    *   Affine translations and scale jittering
    *   Color jitter (brightness/contrast calibration)
    *   *Elastic Deformation* (via PyTorch ElasticTransform) to simulate organic shape variations of glass/plastic inclusions.
*   **Class Imbalance Handling:** Implements PyTorch's `WeightedRandomSampler` during batch formulation to dynamically balance minority classes (e.g., rare defects like inclusions) preventing classifier bias.
*   **Black-Frame Safety Guard:** Built-in heuristic check (`is_black_image`) during inference. If the camera captures a pure black frame (due to camera obstruction, lighting failure, or background transition), the system immediately skips network computation and logs it as `sans_defaut` (or triggers a safety alert) to avoid false classifications.

---

## 5. Installation & Setup

### 1. Clone the repository
```bash
git clone https://github.com/your-username/scot-projet-innovation.git
cd scot-projet-innovation
```

### 2. Create and Activate a Virtual Environment
```bash
# On Windows
python -m venv .venv
.venv\Scripts\activate

# On Linux/macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
Installs PyTorch (configured for CUDA 12.1 acceleration by default), torchvision, and visual/interactive libraries:
```bash
pip install -r requirements.txt
```

---

## 6. Usage Guide

### Phase A: Model Training
To train the neural network, organize your raw images into the `dataset/` directory as described in the directory layout, configure the hyper-parameters in `train.py`'s `CONFIG` dictionary, and run:
```bash
python train.py
```
This script will:
1. Print dataset metrics and class balance distributions.
2. Run training epochs, evaluating performance metrics and computing the custom `CCCC` score.
3. Automatically generate convergence curves (`outputs/training_history.png`) and validation heatmaps (`outputs/confusion_matrix.png`).
4. Save the optimal weights dynamically to `outputs/best_model.pth` and archive progress under `outputs/models_archive/`.

### Phase B: CLI Inference
Test the trained model against isolated sample files using the command-line interface.

*   **Analyze a Single Sample Image:**
    ```bash
    python predict.py --image "test_images/defects/img_test.png"
    ```
*   **Batch Process an Entire Folder of Images:**
    ```bash
    python predict.py --folder "test_images/no_defects/"
    ```
*   **Disable Graphical Matplotlib Plot Popups:**
    ```bash
    python predict.py --image "test_images/defects/img_test.png" --no-plot
    ```

### Phase C: Live Quality Control Dashboard (Streamlit)
To launch the interactive real-time inspection dashboard:
```bash
python -m streamlit run app.py
```
**Dashboard Features:**
*   **Model Selector:** Hot-swapping of models (loads standard `best_model.pth` or any high-scoring checkpoint directly from the `models_archive/` directory).
*   **Live Inspection Feed:** Actively scans the `data_camera/` directory for incoming frames, replicating a physical manufacturing conveyor camera.
*   **Classification & Distribution:** Displays the predicted defect class, color-coded status badges, prediction confidence percentage, and the underlying probability histogram.
*   **Session Diagnostics:** Logs historical detections, counts overall statistics, and dynamically plots defect category frequencies during the active run.

---

## 7. Advanced Optimization (CCCC Score)

During training iterations, SCOT does not rely solely on raw validation accuracy. To select the model checkpoint with the highest real-world reliability and generalization capacity, it monitors the **CCCC Score (Custom Calibration & Consistency Coefficient)**.

The score is calculated as follows:

$$\text{CCCC Score} = \text{Validation Accuracy} - (0.2 \times \text{Validation Loss}) - \text{Overfitting Penalty}$$

Where the **Overfitting Penalty** is defined as:

$$\text{Overfitting Penalty} = 0.5 \times \max\big(0,\, \text{Train Accuracy} - \text{Validation Accuracy}\big)$$

### Rationale behind the formula:
1.  **General Performance Priority:** Rewards models with high validation accuracy.
2.  **Certainty and Entropy Regularization:** Penalizes models that make correct predictions but with low confidence or high cross-entropy loss (via the `0.2 * Validation Loss` penalty).
3.  **Strict Generalization Guard:** Imposes a heavy penalty (`0.5`) on models starting to overfit (where training accuracy starts diverging from validation performance). This guarantees that the deployed checkpoint remains robust to noise and background variances.

---

## 8. License & Acknowledgments

This project is released under the **MIT License**.

Developed as part of the **Innovation Project** during our 3 year masters in engeenering bring advanced deep learning algorithms into high-precision visual inspection systems.
