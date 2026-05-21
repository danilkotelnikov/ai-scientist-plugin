# Domain Templates

The orchestrator selects one template based on the `--domain` flag. Each defines `preferred_libraries`, `experiment_type`, `evaluation_metric`, and any extra manuscript sections.

| Domain | Libraries | Experiment type | Metric | Extra sections |
|---|---|---|---|---|
| ml | torch, torchvision, numpy, matplotlib, scikit-learn, einops | deep_learning_benchmark | validation_accuracy_and_loss | Related Work, Experiments |
| optimization | scipy, cvxpy, pulp, pyomo, numpy | optimization_benchmark | objective_value_and_solve_time | — |
| statistical | scipy, statsmodels, pingouin, numpy, pandas, matplotlib, seaborn | statistical_analysis | p_value_effect_size_and_confidence_interval | Related Work, Statistical Analysis |
| mathematical | sympy, scipy, numpy, matplotlib | mathematical_modeling | symbolic_solution_and_numerical_error | — |
| computational_biology | biopython, numpy, scipy, matplotlib, networkx | bioinformatics_analysis | alignment_score_and_structure_rmsd | Structure Prediction, Machine Learning for Design |
| software_engineering | pytest, hypothesis, black, mypy, pylint, numpy | software_benchmark | performance_and_correctness | Architecture, Implementation Details, Benchmarks |
