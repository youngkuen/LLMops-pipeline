"""ML 방법론 하네스 게이트 — Logic Layer
생성된 ML 코드의 방법론적 무결성을 AST(추상구문트리) 기반으로 검사한다.

정규식이 아닌 AST를 쓰는 이유: 변수명을 바꿔 써도(예: X_test를 xt로 재할당) 실제
데이터가 어디로 흘러가는지 추적해 탐지하기 위함이다.
(교수 자문 2026-06-30: 정규식 검출은 동적 변수명으로 우회 가능하다는 지적을 반영)

위반 항목은 문자열 리스트로 반환하며, 빈 리스트는 통과를 의미한다.
"""
from __future__ import annotations
import ast


def _collect_import_aliases(tree: ast.AST) -> dict[str, str]:
    """`import X as Y` / `from mod import name as alias`의 별칭을 원래 이름으로 해석."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name
    return aliases


def _resolve_call_name(node: ast.Call, import_aliases: dict[str, str]) -> str | None:
    """호출 대상의 정규 이름을 해석한다 (import as 별칭 대응).
    메서드 호출(예: scaler.fit(...))은 속성명을 그대로 사용한다."""
    func = node.func
    if isinstance(func, ast.Name):
        return import_aliases.get(func.id, func.id)
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _build_alias_map(tree: ast.AST) -> dict[str, str]:
    """`a = b` 형태의 단순 변수 재대입을 원본 이름으로 체인 해석한다 (변수명 은닉 대응)."""
    raw: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    raw[target.id] = node.value.id

    def resolve(name: str, seen: frozenset[str] = frozenset()) -> str:
        if name not in raw or name in seen:
            return name
        return resolve(raw[name], seen | {name})

    return {name: resolve(name) for name in raw}


def _resolve_name(node: ast.AST, alias_map: dict[str, str]) -> str | None:
    return alias_map.get(node.id, node.id) if isinstance(node, ast.Name) else None


def _display_name(node: ast.AST, alias_map: dict[str, str]) -> str:
    """메시지 표시용: 별칭이면 '코드상 이름(=실제 이름)' 형태로 우회 사실을 드러낸다."""
    if not isinstance(node, ast.Name):
        return "?"
    resolved = alias_map.get(node.id, node.id)
    return node.id if node.id == resolved else f"{node.id}(={resolved})"


class _Split:
    """`a, b, c, d = train_test_split(...)` 한 건.
    sklearn의 고정 반환 순서(train, test, train, test)로 실제 변수명과 무관하게
    train/test 소속을 판별한다."""

    def __init__(self, call: ast.Call, train: set[str], test: set[str]) -> None:
        self.call = call
        self.train = train
        self.test = test


def _find_splits(tree: ast.AST, import_aliases: dict[str, str]) -> list[_Split]:
    splits: list[_Split] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        if _resolve_call_name(node.value, import_aliases) != "train_test_split":
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Tuple):
            continue
        elts = node.targets[0].elts
        if len(elts) != 4 or not all(isinstance(e, ast.Name) for e in elts):
            continue
        names = [e.id for e in elts]
        splits.append(_Split(
            call=node.value,
            train={names[0], names[2]},  # X_train, y_train (반환 위치 0, 2)
            test={names[1], names[3]},   # X_test, y_test (반환 위치 1, 3)
        ))
    return splits


def _parse(code: str) -> ast.AST | None:
    try:
        return ast.parse(code)
    except SyntaxError:
        return None


def check_leakage(code: str) -> list[str]:
    """데이터 누수: 전처리기·모델이 테스트 데이터로 fit되거나, SMOTE가 학습 데이터가
    아닌 데이터에 적용되는지 검사한다. 변수를 재할당(별칭)해도 탐지된다."""
    tree = _parse(code)
    if tree is None:
        return []

    import_aliases = _collect_import_aliases(tree)
    alias_map = _build_alias_map(tree)
    splits = _find_splits(tree, import_aliases)
    test_names = {n for s in splits for n in s.test}
    train_names = {n for s in splits for n in s.train}

    violations: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and node.args):
            continue
        call_name = _resolve_call_name(node, import_aliases)
        first_arg = node.args[0]
        arg_name = _resolve_name(first_arg, alias_map)
        if arg_name is None:
            continue

        if call_name in ("fit", "fit_transform") and arg_name in test_names:
            violations.append(
                f"데이터 누수 — 테스트 데이터로 fit이 호출됨 (변수: {_display_name(first_arg, alias_map)}): "
                "X_train으로만 fit하고 X_test는 transform만 적용하세요"
            )
        elif call_name == "fit_resample" and train_names and arg_name not in train_names:
            violations.append(
                f"데이터 누수 — SMOTE가 학습 데이터가 아닌 데이터에 적용됨 "
                f"(변수: {_display_name(first_arg, alias_map)}): "
                "train_test_split 이후 X_train, y_train에만 적용하세요"
            )
    return violations


_CV_CLASSES = {"RandomizedSearchCV", "GridSearchCV"}


def _collect_cv_var_names(tree: ast.AST, import_aliases: dict[str, str]) -> set[str]:
    """`search = RandomizedSearchCV(...)` 형태로 생성된 CV 탐색 객체의 변수명을 수집."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        if _resolve_call_name(node.value, import_aliases) in _CV_CLASSES:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _is_cv_fit_call(
    node: ast.Call, import_aliases: dict[str, str], cv_var_names: set[str], alias_map: dict[str, str]
) -> bool:
    """`<cv 객체>.fit(...)` 호출인지 판별. 변수 경유(search.fit)와 체이닝
    (RandomizedSearchCV(...).fit(...)) 둘 다 인식한다."""
    if not (isinstance(node.func, ast.Attribute) and node.func.attr == "fit"):
        return False
    receiver = node.func.value
    if isinstance(receiver, ast.Call):
        return _resolve_call_name(receiver, import_aliases) in _CV_CLASSES
    if isinstance(receiver, ast.Name):
        return alias_map.get(receiver.id, receiver.id) in cv_var_names
    return False


def check_cv_integrity(code: str) -> list[str]:
    """교차검증 무결성: RandomizedSearchCV/GridSearchCV가 학습 데이터가 아닌 전체·테스트
    데이터로 수행되지 않았는지 검사한다 (하이퍼파라미터 탐색 자체의 데이터 누수 방지)."""
    tree = _parse(code)
    if tree is None:
        return []

    import_aliases = _collect_import_aliases(tree)
    alias_map = _build_alias_map(tree)
    splits = _find_splits(tree, import_aliases)
    train_names = {n for s in splits for n in s.train}
    if not train_names:
        return []  # 분할 정보를 알 수 없으면 오탐 방지를 위해 건너뜀

    cv_var_names = _collect_cv_var_names(tree, import_aliases)

    violations: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and node.args):
            continue
        if not _is_cv_fit_call(node, import_aliases, cv_var_names, alias_map):
            continue
        first_arg = node.args[0]
        arg_name = _resolve_name(first_arg, alias_map)
        if arg_name is not None and arg_name not in train_names:
            violations.append(
                "교차검증 무결성 위반 — RandomizedSearchCV/GridSearchCV가 학습 데이터가 아닌 "
                f"데이터로 수행됨 (변수: {_display_name(first_arg, alias_map)}): "
                "train_test_split 이후 X_train, y_train으로만 fit하세요"
            )
    return violations


def check_smote_order(code: str, task_type: str = "classification") -> list[str]:
    """SMOTE 순서: train_test_split 이전에 SMOTE가 적용되지 않았는지 검사한다.
    호출 순서(줄 번호) 기준이라 변수명·import 별칭과 무관하게 탐지된다."""
    if task_type != "classification":
        return []
    tree = _parse(code)
    if tree is None:
        return []

    import_aliases = _collect_import_aliases(tree)
    splits = _find_splits(tree, import_aliases)
    if not splits:
        return []
    split_line = min(s.call.lineno for s in splits)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _resolve_call_name(node, import_aliases) == "fit_resample":
            if node.lineno < split_line:
                return [
                    "SMOTE 순서 오류 — SMOTE가 train_test_split 이전에 적용됨: "
                    "split 이후 X_train, y_train에만 적용하세요"
                ]
    return []


def check_evaluation(code: str) -> list[str]:
    """평가 무결성: 최종 predict가 X_train으로만 수행되지 않았는지 검사."""
    tree = _parse(code)
    if tree is None:
        return []

    import_aliases = _collect_import_aliases(tree)
    alias_map = _build_alias_map(tree)
    splits = _find_splits(tree, import_aliases)
    test_names = {n for s in splits for n in s.test}
    train_names = {n for s in splits for n in s.train}

    predict_on_train = predict_on_test = False
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and node.args):
            continue
        if _resolve_call_name(node, import_aliases) != "predict":
            continue
        arg_name = _resolve_name(node.args[0], alias_map)
        if arg_name in test_names:
            predict_on_test = True
        elif arg_name in train_names:
            predict_on_train = True

    if predict_on_train and not predict_on_test:
        return ["평가 오류 — 최종 예측이 X_train으로만 수행됨: X_test로 평가해야 합니다"]
    return []


# random_state를 항상 안전하게 받는 것으로 확인된 대상만 강제한다.
# (KNN·나이브베이즈·LinearRegression·SVR 등은 random_state 자체가 없어 TypeError가
#  나므로, 확신 없는 추정기는 게이트에서 강제하지 않고 프롬프트로만 유도한다.)
_SEED_REQUIRED_CALLS = {"train_test_split", "RandomizedSearchCV", "GridSearchCV", "SMOTE"}


def _has_fixed_random_state(node: ast.Call) -> bool:
    kw = next((k for k in node.keywords if k.arg == "random_state"), None)
    return kw is not None and isinstance(kw.value, ast.Constant) and kw.value.value is not None


def check_reproducibility(code: str) -> list[str]:
    """재현성: 분할·교차검증·오버샘플링에 고정된 random_state가 설정됐는지 검사한다.
    `shuffle=False`로 순서가 고정된 분할(시계열)은 random_state가 무의미하므로 예외."""
    tree = _parse(code)
    if tree is None:
        return []

    import_aliases = _collect_import_aliases(tree)
    violations: list[str] = []
    seen: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call_name = _resolve_call_name(node, import_aliases)
        if call_name not in _SEED_REQUIRED_CALLS or call_name in seen:
            continue

        if call_name == "train_test_split":
            shuffle_kw = next((k for k in node.keywords if k.arg == "shuffle"), None)
            if (
                shuffle_kw is not None
                and isinstance(shuffle_kw.value, ast.Constant)
                and shuffle_kw.value.value is False
            ):
                continue  # 순서 고정 분할 — random_state가 적용되지 않으므로 무관

        if not _has_fixed_random_state(node):
            seen.add(call_name)
            violations.append(
                f"재현성 누락 — {call_name}에 random_state가 고정되지 않음: "
                "random_state=42처럼 고정값을 지정하세요"
            )
    return violations


def check_timeseries_split(code: str, task_type: str = "classification") -> list[str]:
    """시계열 누수: train_test_split 호출에 shuffle=False가 명시됐는지 검사한다
    (호출 단위로 검사하므로 여러 split이 있어도 각각 정확히 판정된다)."""
    if task_type != "timeseries":
        return []
    tree = _parse(code)
    if tree is None:
        return []

    import_aliases = _collect_import_aliases(tree)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _resolve_call_name(node, import_aliases) == "train_test_split"):
            continue
        shuffle_kw = next((kw for kw in node.keywords if kw.arg == "shuffle"), None)
        is_false = (
            shuffle_kw is not None
            and isinstance(shuffle_kw.value, ast.Constant)
            and shuffle_kw.value.value is False
        )
        if not is_false:
            return [
                "시계열 누수 — train_test_split에 shuffle=False가 없습니다: "
                "시간순으로 분할하세요 (train_test_split(..., shuffle=False) 또는 인덱스 슬라이싱)"
            ]
    return []


def run_all(code: str, task_type: str = "classification") -> list[str]:
    """모든 게이트를 실행하고 위반 목록을 반환한다."""
    violations: list[str] = []
    violations.extend(check_leakage(code))
    violations.extend(check_cv_integrity(code))
    violations.extend(check_smote_order(code, task_type))
    violations.extend(check_evaluation(code))
    violations.extend(check_timeseries_split(code, task_type))
    violations.extend(check_reproducibility(code))
    return violations
