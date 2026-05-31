# Comparação de Modelos — Benign vs Threat

## UNSW-NB15

- Registros: 4,000 (3,524 benign / 476 threat)
- Treino/Teste: 3,200 / 800 | Features: 35 | Seed: 42
- Melhor modelo (F1): **LightGBM**

| Modelo | Família | Acc | Bal.Acc | Precisão | Recall | F1 | ROC-AUC | PR-AUC | CV F1 (μ±σ) | Treino(s) |
|---|---|---|---|---|---|---|---|---|---|---|
| LightGBM | boosting | 0.9938 | 0.9873 | 0.9688 | 0.9789 | 0.9738 | 0.9994 | 0.9957 | — | 0.2 |
| HistGradientBoosting | boosting | 0.9938 | 0.9828 | 0.9787 | 0.9684 | 0.9735 | 0.9995 | 0.9960 | — | 1.93 |
| XGBoost | boosting | 0.9938 | 0.9828 | 0.9787 | 0.9684 | 0.9735 | 0.9997 | 0.9976 | — | 0.31 |
| Ensemble | ensemble | 0.9938 | 0.9828 | 0.9787 | 0.9684 | 0.9735 | 0.9996 | 0.9969 | — | 0.0 |
| RandomForest | bagging | 0.9900 | 0.9761 | 0.9579 | 0.9579 | 0.9579 | 0.9993 | 0.9945 | — | 0.26 |
| ExtraTrees | bagging | 0.9900 | 0.9716 | 0.9677 | 0.9474 | 0.9574 | 0.9994 | 0.9957 | — | 0.2 |
| DecisionTree | tree | 0.9862 | 0.9603 | 0.9565 | 0.9263 | 0.9412 | 0.9603 | 0.8948 | — | 0.01 |
| MLP | neural | 0.9862 | 0.9512 | 0.9773 | 0.9053 | 0.9399 | 0.9872 | 0.9690 | — | 0.39 |
| LogisticRegression | linear | 0.9838 | 0.9771 | 0.9020 | 0.9684 | 0.9340 | 0.9860 | 0.9176 | — | 0.02 |
| KNN | instance | 0.9762 | 0.9046 | 0.9872 | 0.8105 | 0.8902 | 0.9979 | 0.9838 | — | 0.0 |
| GaussianNB | probabilistic | 0.8750 | 0.9109 | 0.4866 | 0.9579 | 0.6454 | 0.9586 | 0.7649 | — | 0.0 |
