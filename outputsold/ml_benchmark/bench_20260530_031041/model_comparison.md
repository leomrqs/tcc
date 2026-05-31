# Comparação de Modelos — Benign vs Threat

## CIC-IDS2017

- Registros: 8,000 (6,465 benign / 1,535 threat)
- Treino/Teste: 6,400 / 1,600 | Features: 45 | Seed: 42
- Melhor modelo (F1): **LightGBM**

| Modelo | Família | Acc | Bal.Acc | Precisão | Recall | F1 | ROC-AUC | PR-AUC | CV F1 (μ±σ) | Treino(s) |
|---|---|---|---|---|---|---|---|---|---|---|
| LightGBM | boosting | 0.9969 | 0.9968 | 0.9871 | 0.9967 | 0.9919 | 0.9999 | 0.9995 | 0.9882±0.0037 | 0.27 |
| RandomForest | bagging | 0.9962 | 0.9915 | 0.9967 | 0.9837 | 0.9902 | 0.9996 | 0.9986 | 0.9724±0.0071 | 0.31 |
| HistGradientBoosting | boosting | 0.9956 | 0.9948 | 0.9839 | 0.9935 | 0.9887 | 0.9996 | 0.9987 | 0.9861±0.0049 | 1.98 |
| Ensemble | ensemble | 0.9956 | 0.9936 | 0.9870 | 0.9902 | 0.9886 | 0.9999 | 0.9997 | — | 0.0 |
| XGBoost | boosting | 0.9950 | 0.9919 | 0.9870 | 0.9870 | 0.9870 | 0.9997 | 0.9988 | 0.9833±0.0053 | 0.45 |
| DecisionTree | tree | 0.9919 | 0.9863 | 0.9804 | 0.9772 | 0.9788 | 0.9863 | 0.9624 | 0.9677±0.0104 | 0.05 |
| ExtraTrees | bagging | 0.9825 | 0.9830 | 0.9292 | 0.9837 | 0.9557 | 0.9990 | 0.9966 | 0.9517±0.0013 | 0.19 |
| LogisticRegression | linear | 0.9300 | 0.9430 | 0.7456 | 0.9642 | 0.8409 | 0.9792 | 0.9135 | 0.8438±0.0022 | 0.06 |
| GaussianNB | probabilistic | 0.7800 | 0.8564 | 0.4652 | 0.9805 | 0.6310 | 0.9172 | 0.7082 | 0.6395±0.0198 | 0.01 |
