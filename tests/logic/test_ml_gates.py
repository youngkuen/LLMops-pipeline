"""ML 방법론 게이트 단위 테스트 — AST 기반 검사 (변수명 우회 방지 포함)"""
from app.agents import ml_gates

SPLIT = "X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)\n"


# ─────────── check_leakage — 변수명을 바꿔도 탐지되는가 (핵심 목적) ───────────

def test_leakage_detects_fit_on_renamed_test_variable():
    code = SPLIT + "xt = X_test\nscaler.fit(xt)\n"
    violations = ml_gates.check_leakage(code)
    assert len(violations) == 1
    assert "xt" in violations[0]


def test_leakage_allows_fit_on_train():
    code = SPLIT + "scaler.fit(X_train)\nmodel.fit(X_train, y_train)\n"
    assert ml_gates.check_leakage(code) == []


def test_leakage_detects_smote_on_aliased_non_train_data():
    # SMOTE가 split 이후에 호출됐지만, 대상이 X_train이 아니라 원본 X의 별칭
    code = SPLIT + "leaky_ref = X\nX_res, y_res = SMOTE().fit_resample(leaky_ref, y)\n"
    violations = ml_gates.check_leakage(code)
    assert any("leaky_ref" in v for v in violations)


def test_leakage_allows_smote_on_train_data():
    code = SPLIT + "X_res, y_res = SMOTE().fit_resample(X_train, y_train)\n"
    assert ml_gates.check_leakage(code) == []


def test_leakage_skips_smote_check_when_no_split_found():
    # 분할 정보를 알 수 없으면(오탐 방지) SMOTE 검사를 건너뛴다
    code = "X_res, y_res = SMOTE().fit_resample(X, y)\n"
    assert ml_gates.check_leakage(code) == []


# ─────────── check_smote_order — import 별칭이 있어도 탐지되는가 ───────────

def test_smote_order_detects_before_split():
    code = "X_res, y_res = SMOTE().fit_resample(X, y)\n" + SPLIT
    violations = ml_gates.check_smote_order(code)
    assert len(violations) == 1


def test_smote_order_recognizes_renamed_import():
    code = (
        "from sklearn.model_selection import train_test_split as tts\n"
        "X_train, X_test, y_train, y_test = tts(X, y, test_size=0.2)\n"
        "X_res, y_res = SMOTE().fit_resample(X_train, y_train)\n"
    )
    assert ml_gates.check_smote_order(code) == []


# ─────────── check_cv_integrity — RandomizedSearchCV/GridSearchCV 학습 데이터 검사 ───────────

def test_cv_integrity_flags_fit_on_full_data():
    code = SPLIT + (
        "search = RandomizedSearchCV(model, param_distributions=grid, cv=3)\n"
        "search.fit(X, y)\n"
    )
    violations = ml_gates.check_cv_integrity(code)
    assert len(violations) == 1
    assert "X" in violations[0]


def test_cv_integrity_allows_fit_on_train():
    code = SPLIT + (
        "search = RandomizedSearchCV(model, param_distributions=grid, cv=3)\n"
        "search.fit(X_train, y_train)\n"
    )
    assert ml_gates.check_cv_integrity(code) == []


def test_cv_integrity_detects_chained_call():
    code = SPLIT + "model = RandomizedSearchCV(est, param_distributions=grid, cv=3).fit(X, y).best_estimator_\n"
    assert len(ml_gates.check_cv_integrity(code)) == 1


def test_cv_integrity_recognizes_aliased_cv_object():
    code = SPLIT + (
        "search = RandomizedSearchCV(model, param_distributions=grid, cv=3)\n"
        "search2 = search\n"
        "search2.fit(X, y)\n"
    )
    assert len(ml_gates.check_cv_integrity(code)) == 1


def test_cv_integrity_skips_when_cv_not_used():
    code = SPLIT + "model.fit(X_train, y_train)\n"
    assert ml_gates.check_cv_integrity(code) == []


# ─────────── check_evaluation ───────────

def test_evaluation_flags_predict_on_train_only():
    code = SPLIT + "model.fit(X_train, y_train)\ny_pred = model.predict(X_train)\n"
    violations = ml_gates.check_evaluation(code)
    assert len(violations) == 1


def test_evaluation_passes_when_predicting_on_test():
    code = SPLIT + "model.fit(X_train, y_train)\ny_pred = model.predict(X_test)\n"
    assert ml_gates.check_evaluation(code) == []


# ─────────── check_reproducibility — random_state 고정 검사 ───────────

def test_reproducibility_flags_missing_seed_on_split():
    code = "X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)\n"
    violations = ml_gates.check_reproducibility(code)
    assert len(violations) == 1
    assert "train_test_split" in violations[0]


def test_reproducibility_passes_when_seed_present():
    assert ml_gates.check_reproducibility(SPLIT) == []


def test_reproducibility_skips_shuffle_false_split():
    # 시계열처럼 순서가 고정된 분할은 random_state가 무의미하므로 예외
    code = "X_train, X_test, y_train, y_test = train_test_split(X, y, shuffle=False)\n"
    assert ml_gates.check_reproducibility(code) == []


def test_reproducibility_flags_missing_seed_on_cv_search():
    code = SPLIT + "search = RandomizedSearchCV(model, param_distributions=grid, cv=3)\n"
    violations = ml_gates.check_reproducibility(code)
    assert any("RandomizedSearchCV" in v for v in violations)


def test_reproducibility_flags_missing_seed_on_smote():
    code = SPLIT + "X_res, y_res = SMOTE().fit_resample(X_train, y_train)\n"
    violations = ml_gates.check_reproducibility(code)
    assert any("SMOTE" in v for v in violations)


def test_reproducibility_ignores_estimators_without_random_state_param():
    # LogisticRegression 등은 게이트에서 강제하지 않는다 (KNN·SVR 등 random_state가
    # 아예 없는 추정기까지 강제하면 TypeError 위험이 있어 확실한 대상만 강제)
    code = SPLIT + "model = LogisticRegression()\nmodel.fit(X_train, y_train)\n"
    assert ml_gates.check_reproducibility(code) == []


def test_timeseries_split_flags_random_shuffle():
    code = "X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)"
    violations = ml_gates.check_timeseries_split(code, "timeseries")
    assert len(violations) == 1
    assert "shuffle=False" in violations[0]


def test_timeseries_split_allows_no_shuffle():
    code = "train_test_split(X, y, test_size=0.2, shuffle=False)"
    assert ml_gates.check_timeseries_split(code, "timeseries") == []


def test_timeseries_split_allows_index_slicing():
    code = "X_train = X.iloc[:80]\nX_test = X.iloc[80:]"
    assert ml_gates.check_timeseries_split(code, "timeseries") == []


def test_timeseries_gate_ignored_for_non_timeseries():
    code = "train_test_split(X, y, test_size=0.2)"
    assert ml_gates.check_timeseries_split(code, "regression") == []
    assert ml_gates.check_timeseries_split(code, "classification") == []


def test_run_all_includes_timeseries_gate():
    code = "train_test_split(X, y, test_size=0.2)"
    # 시계열 태스크에서는 run_all이 셔플 위반을 포함해야 한다
    assert any("shuffle=False" in v for v in ml_gates.run_all(code, "timeseries"))
    # 회귀에서는 포함되지 않는다
    assert not any("shuffle=False" in v for v in ml_gates.run_all(code, "regression"))
