# Third-party dependencies

Every open-source library used by this project is recorded here with its
licence (CodeSplash Guidelines 7.3).

| Package | Version | Licence | Used for |
|---|---|---|---|
| pandas | 2.2.3 | BSD 3-Clause | Reading the dataset CSVs in `ml/seed.py` |
| PyYAML | 6.0.2 | MIT | Reading `config/weights.yaml` and `config/cost_bands.yaml` |
| NumPy | 2.1.3 | BSD 3-Clause | Feature arithmetic and the MAE/RMSE metrics |
| LightGBM | 4.5.0 | MIT | The visitor pressure regressor (`ml/train_pressure.py`) |
| passlib | 1.7.4 | BSD 2-Clause | argon2 password hashing (`api/services/security.py`) |
| argon2-cffi | 25.1.0 | MIT | The argon2 implementation passlib calls |
| PyJWT | 2.10.1 | MIT | Signing and decoding the authority JWT |
