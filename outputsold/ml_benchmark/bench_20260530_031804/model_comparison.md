# Comparação de Modelos — Benign vs Threat

## CIC-IDS2017

- Registros: 6,000 (4,857 benign / 1,143 threat)
- Treino/Teste: 4,800 / 1,200 | Features: 45 | Seed: 42
- Melhor modelo (F1): **XGBoost**

| Modelo | Família | Acc | Bal.Acc | Precisão | Recall | F1 | ROC-AUC | PR-AUC | CV F1 (μ±σ) | Treino(s) |
|---|---|---|---|---|---|---|---|---|---|---|
| XGBoost | boosting | 0.9983 | 0.9973 | 0.9956 | 0.9956 | 0.9956 | 0.9997 | 0.9989 | — | 0.4 |
| LightGBM | boosting | 0.9975 | 0.9968 | 0.9913 | 0.9956 | 0.9935 | 0.9998 | 0.9993 | — | 0.21 |
| HistGradientBoosting | boosting | 0.9975 | 0.9951 | 0.9956 | 0.9913 | 0.9934 | 0.9999 | 0.9997 | — | 1.83 |
| Ensemble | ensemble | 0.9975 | 0.9951 | 0.9956 | 0.9913 | 0.9934 | 0.9997 | 0.9989 | — | 0.0 |
| RandomForest | bagging | 0.9925 | 0.9837 | 0.9911 | 0.9694 | 0.9801 | 0.9993 | 0.9976 | — | 0.25 |
| ExtraTrees | bagging | 0.9833 | 0.9780 | 0.9447 | 0.9694 | 0.9569 | 0.9989 | 0.9958 | — | 0.18 |
| DecisionTree | tree | 0.9817 | 0.9703 | 0.9520 | 0.9520 | 0.9520 | 0.9703 | 0.9154 | — | 0.05 |
| LogisticRegression | linear | 0.9275 | 0.9368 | 0.7415 | 0.9520 | 0.8337 | 0.9796 | 0.9158 | — | 0.04 |
| GaussianNB | probabilistic | 0.7750 | 0.8526 | 0.4581 | 0.9782 | 0.6240 | 0.9270 | 0.7210 | — | 0.01 |
