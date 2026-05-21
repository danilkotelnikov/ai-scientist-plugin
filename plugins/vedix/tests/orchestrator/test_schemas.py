import pytest
import jsonschema
from mcp.lib.orchestrator.schemas import (
    IDEATION_SCHEMA, HYPOTHESIS_SCHEMA, REVIEW_SCHEMA,
    EXPERIMENT_RESULT_SCHEMA, validate_against,
)


def test_ideation_schema_passes_valid():
    valid = {
        "Name": "ridge_hetero",
        "Title": "Ridge under heteroscedastic noise",
        "Short_Hypothesis": "Ridge beats OLS as alpha grows.",
        "Related_Work": "ESL covers ridge under homoscedastic noise.",
        "Abstract": "We test whether ridge regression maintains its variance reduction advantage when noise variance scales with input magnitude.",
        "Experiments": [{"name": "sweep", "metric": "MSE"}],
        "Risks": ["small effect size"],
    }
    validate_against(valid, IDEATION_SCHEMA)


def test_ideation_schema_rejects_missing_required():
    invalid = {"Name": "x"}
    with pytest.raises(jsonschema.ValidationError, match="Title"):
        validate_against(invalid, IDEATION_SCHEMA)


def test_hypothesis_schema_passes_valid():
    valid = {
        "hypothesis": "Ridge has lower test MSE than OLS for alpha >= 2.",
        "math_models": "y = X*beta + eps where eps ~ N(0, sigma^2 * (1+alpha*||x||^2/p))",
        "statistical_framework": {
            "null": "no difference", "alt": "ridge < ols",
            "test": "paired t-test", "alpha": 0.05,
            "correction": "bonferroni", "effect_size": "cohens_d",
        },
        "methodology": "monte carlo over alpha grid",
        "dependencies": ["numpy", "scikit-learn"],
    }
    validate_against(valid, HYPOTHESIS_SCHEMA)


def test_review_schema_passes_valid():
    valid = {
        "Summary": "Solid synthetic benchmark.",
        "Strengths": ["clean protocol"],
        "Weaknesses": ["small effect"],
        "Originality": 2, "Quality": 3, "Clarity": 3, "Significance": 2,
        "Soundness": 3, "Presentation": 3, "Contribution": 2,
        "Overall": 5, "Confidence": 4,
        "Decision": "Borderline / Weak Accept",
        "Questions": ["why fixed lambda?"],
        "Limitations": ["isotropic design only"],
        "Actionable_Fixes": ["fix monotonicity claim"],
    }
    validate_against(valid, REVIEW_SCHEMA)


def test_review_schema_rejects_score_out_of_range():
    invalid = {
        "Summary": "x", "Strengths": [], "Weaknesses": [],
        "Originality": 99, "Quality": 1, "Clarity": 1, "Significance": 1,
        "Soundness": 1, "Presentation": 1, "Contribution": 1,
        "Overall": 1, "Confidence": 1,
        "Decision": "Reject", "Questions": [], "Limitations": [],
        "Actionable_Fixes": [],
    }
    with pytest.raises(jsonschema.ValidationError):
        validate_against(invalid, REVIEW_SCHEMA)


def test_experiment_result_schema_passes_valid():
    valid = {
        "exit_code": 0, "results_csv_present": True,
        "npy_files": ["data_main.npy"], "figures": ["plot_results.png"],
        "fix_attempts": 0, "stdout_summary": "...", "stderr_summary": "",
    }
    validate_against(valid, EXPERIMENT_RESULT_SCHEMA)
