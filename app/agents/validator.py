"""허용 라이브러리 화이트리스트 검증 — Logic Layer"""
import ast
from dataclasses import dataclass, field

ALLOWED_TOP_LEVEL = {
    "pandas", "numpy", "scipy", "sklearn", "xgboost", "lightgbm",
    "matplotlib", "math", "statistics", "collections",
    "itertools", "io", "json", "re",
    "warnings", "imblearn",
}


@dataclass
class ValidationResult:
    is_valid: bool
    blocked_imports: list[str] = field(default_factory=list)
    error_message: str = ""


def validate_code(source_code: str) -> ValidationResult:
    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        first_line = next((ln for ln in source_code.splitlines() if ln.strip()), "")
        preview = first_line[:120]
        return ValidationResult(
            is_valid=False,
            error_message=f"문법 오류: {e} | 코드 첫 줄: {preview!r}",
        )

    blocked = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top not in ALLOWED_TOP_LEVEL:
                    blocked.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            top = module.split(".")[0]
            if top and top not in ALLOWED_TOP_LEVEL:
                blocked.append(module)

    if blocked:
        unique = list(dict.fromkeys(blocked))
        return ValidationResult(
            is_valid=False,
            blocked_imports=unique,
            error_message=f"허용되지 않는 라이브러리: {', '.join(unique)}",
        )
    return ValidationResult(is_valid=True)
