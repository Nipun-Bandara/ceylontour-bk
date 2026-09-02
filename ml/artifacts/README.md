# Artifacts

Everything in this folder is **generated**, and everything except this file is
gitignored.

```bash
python ml/train_pressure.py
```

```bash
python ml/evaluate.py
```

| File | Written by | What it is |
|---|---|---|
| `pressure-v1.0.txt` | `train_pressure.py` | The LightGBM model |
| `pressure-v1.0.features.json` | `train_pressure.py` | Feature order and region categories, so inference matches training |
| `model_card.md` | `evaluate.py` | What the model predicts, how well, and its limitations |

The model card is not written by hand. It reports whatever the evaluation
measured, including the case where the model loses to the seasonal-average
baseline. If that happens, the card says so and so does the demo.

These are gitignored because a model card is only true of the data it was
generated from. Committing one trained on example rows would put fabricated
accuracy numbers in the repository, which is the opposite of what a model card
is for. Regenerate them once the real SLTDA series is loaded.
