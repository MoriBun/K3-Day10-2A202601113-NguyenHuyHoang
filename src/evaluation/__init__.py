from typing import Any

from .testset import build_test_set

__all__ = ["EvaluationBundle", "JudgeVerdict", "build_test_set", "evaluate_pipeline"]


def __getattr__(name: str) -> Any:
    """Avoid importing optional evaluation dependencies when only building a test set."""
    if name in {"EvaluationBundle", "JudgeVerdict", "evaluate_pipeline"}:
        from .metrics import EvaluationBundle, JudgeVerdict, evaluate_pipeline

        return {
            "EvaluationBundle": EvaluationBundle,
            "JudgeVerdict": JudgeVerdict,
            "evaluate_pipeline": evaluate_pipeline,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
