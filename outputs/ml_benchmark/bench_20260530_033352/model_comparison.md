# Comparação de Modelos — Benign vs Threat

## CIC-IDS2017

- Registros: 30,000 (24,179 benign / 5,821 threat)
- Treino/Teste: 24,000 / 6,000 | Features: 45 | Seed: 42
- Melhor modelo (F1): **XGBoost**

| Modelo | Família | Acc | Bal.Acc | Precisão | Recall | F1 | ROC-AUC | PR-AUC | CV F1 (μ±σ) | Treino(s) |
|---|---|---|---|---|---|---|---|---|---|---|
| XGBoost | boosting | 0.9988 | 0.9983 | 0.9966 | 0.9974 | 0.9970 | 0.9999 | 0.9996 | — | 0.76 |
| LightGBM | boosting | 0.9988 | 0.9983 | 0.9966 | 0.9974 | 0.9970 | 0.9999 | 0.9997 | — | 0.55 |
| Ensemble | ensemble | 0.9985 | 0.9974 | 0.9966 | 0.9957 | 0.9961 | 0.9998 | 0.9990 | — | 0.0 |
| HistGradientBoosting | boosting | 0.9972 | 0.9960 | 0.9914 | 0.9940 | 0.9927 | 0.9998 | 0.9991 | — | 1.79 |
| DecisionTree | tree | 0.9960 | 0.9933 | 0.9905 | 0.9888 | 0.9897 | 0.9933 | 0.9816 | — | 0.19 |
| RandomForest | bagging | 0.9960 | 0.9913 | 0.9957 | 0.9837 | 0.9896 | 0.9997 | 0.9982 | — | 0.52 |
| ExtraTrees | bagging | 0.9815 | 0.9833 | 0.9236 | 0.9863 | 0.9539 | 0.9986 | 0.9950 | — | 0.33 |
| LogisticRegression | linear | 0.9320 | 0.9330 | 0.7662 | 0.9347 | 0.8421 | 0.9787 | 0.9192 | — | 0.15 |
| GaussianNB | probabilistic | 0.7213 | 0.8160 | 0.4082 | 0.9708 | 0.5748 | 0.9129 | 0.6028 | — | 0.02 |

## UNSW-NB15

- Registros: 30,000 (26,304 benign / 3,696 threat)
- Treino/Teste: 24,000 / 6,000 | Features: 35 | Seed: 42
- Melhor modelo (F1): **RandomForest**

| Modelo | Família | Acc | Bal.Acc | Precisão | Recall | F1 | ROC-AUC | PR-AUC | CV F1 (μ±σ) | Treino(s) |
|---|---|---|---|---|---|---|---|---|---|---|
| RandomForest | bagging | 0.9917 | 0.9848 | 0.9575 | 0.9756 | 0.9665 | 0.9996 | 0.9971 | — | 0.45 |
| LightGBM | boosting | 0.9917 | 0.9848 | 0.9575 | 0.9756 | 0.9665 | 0.9996 | 0.9971 | — | 0.43 |
| Ensemble | ensemble | 0.9913 | 0.9852 | 0.9538 | 0.9770 | 0.9652 | 0.9996 | 0.9972 | — | 0.0 |
| XGBoost | boosting | 0.9912 | 0.9851 | 0.9525 | 0.9770 | 0.9646 | 0.9996 | 0.9971 | — | 0.56 |
| ExtraTrees | bagging | 0.9898 | 0.9878 | 0.9357 | 0.9851 | 0.9598 | 0.9995 | 0.9964 | — | 0.35 |
| HistGradientBoosting | boosting | 0.9898 | 0.9855 | 0.9403 | 0.9797 | 0.9596 | 0.9995 | 0.9968 | — | 0.26 |
| DecisionTree | tree | 0.9888 | 0.9750 | 0.9528 | 0.9567 | 0.9548 | 0.9764 | 0.9360 | — | 0.1 |
| LogisticRegression | linear | 0.9878 | 0.9913 | 0.9132 | 0.9959 | 0.9528 | 0.9986 | 0.9831 | — | 0.11 |
| GaussianNB | probabilistic | 0.9015 | 0.9380 | 0.5565 | 0.9865 | 0.7116 | 0.9807 | 0.8234 | — | 0.03 |
