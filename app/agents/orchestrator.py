"""Orchestrator — Logic Layer
Mode A/B 전체 파이프라인 실행을 조율한다.
각 단계에서 progress_callback을 호출하여 UI에 진행 상황을 알린다.

개선 루프(교수 자문 2026-07): 코드 생성→검증→실행→진단을 최대 MAX_IMPROVE_ROUNDS회 반복하며,
진단이 '신뢰 가능'이 되거나 성능이 개선될 때까지 진단 결과를 피드백으로 코드를 다시 생성한다.
전처리·모델 개선을 한 루프에서 처리(통합 개선 루프).
"""
from __future__ import annotations
import uuid
from typing import Callable, Optional
from app.domain.models import (
    AnalysisResult, AnalysisSession, ModeARequest, ModeBRequest,
    OrchestratorResult, SessionMode, SessionStatus,
)
from app.agents.plan_agent import PlanAgent
from app.agents.code_agent import CodeAgent
from app.agents.chat_agent import ChatAgent
from app.agents.eval_agent import EvalAgent
from app.agents.spec_agent import SpecAgent
from app.agents.validator import validate_code
from app.executor.code_executor import run_code
from app.loaders.anonymizer import mask_text
from app.loaders.csv_loader import infer_schema, load_dataframe, schema_to_text
from app.providers.base import LLMProvider
from app.storage.session_store import SessionStore

ProgressCallback = Callable[[str], None]

def _fmt_cost(usd: float) -> str:
    return f"${usd:.4f}"


class Orchestrator:
    MAX_IMPROVE_ROUNDS = 3  # 통합 개선 루프 최대 반복 횟수

    def __init__(
        self,
        plan_agent: PlanAgent,
        code_agent: CodeAgent,
        session_store: SessionStore,
        chat_agent: Optional[ChatAgent] = None,
        eval_agent: Optional[EvalAgent] = None,
        spec_agent: Optional[SpecAgent] = None,
        llm_provider: Optional[LLMProvider] = None,
    ) -> None:
        self._plan = plan_agent
        self._code = code_agent
        self._store = session_store
        self._chat = chat_agent
        self._eval = eval_agent
        self._spec = spec_agent
        self._llm = llm_provider  # 비용 추적용 (에이전트들과 동일 인스턴스)

    # ── 비용 추적 헬퍼 ────────────────────────────────────────────────

    def _snapshot(self) -> Optional[dict]:
        return self._llm.usage_snapshot() if self._llm else None

    def _notify_cost(self, notify: ProgressCallback, before: Optional[dict], label: str) -> None:
        if self._llm is None or before is None:
            return
        after = self._llm.usage_snapshot()
        d_in = after["input_tokens"] - before["input_tokens"]
        d_out = after["output_tokens"] - before["output_tokens"]
        if d_in == 0 and d_out == 0:
            # 실제 호출이 있었는데 토큰 변화가 없다는 건 캐시 히트라는 뜻 (재현성: 동일 요청 재사용)
            notify(f"  └─ ⚡ {label}: 캐시 재사용 — 동일 요청이라 API 호출 생략 (비용 $0)")
            return
        usd = self._llm.cost_usd({"input_tokens": d_in, "output_tokens": d_out})
        notify(f"  └─ 💰 {label}: 입력 {d_in:,} · 출력 {d_out:,} 토큰 · {_fmt_cost(usd)}")

    def _total_cost(self, before: Optional[dict]) -> Optional[dict]:
        if self._llm is None or before is None:
            return None
        after = self._llm.usage_snapshot()
        d_in = after["input_tokens"] - before["input_tokens"]
        d_out = after["output_tokens"] - before["output_tokens"]
        usd = self._llm.cost_usd({"input_tokens": d_in, "output_tokens": d_out})
        return {"input_tokens": d_in, "output_tokens": d_out, "usd": usd}

    # ──────────────────────── 통합 개선 루프 (공통) ────────────────────

    def _run_improvement_loop(
        self, session: AnalysisSession, plan, schema, df, notify: ProgressCallback
    ) -> tuple[Optional[AnalysisResult], Optional[str]]:
        """코드생성→검증→실행→진단을 최대 MAX_IMPROVE_ROUNDS회 반복.
        가장 성능 좋은 결과를 반환한다. 반환: (result | None, error_message | None)."""
        task_type = getattr(plan, "task_type", "classification")
        feedback = ""
        best_result: Optional[AnalysisResult] = None
        best_score: Optional[float] = None

        for i in range(self.MAX_IMPROVE_ROUNDS):
            tag = f"({i + 1}/{self.MAX_IMPROVE_ROUNDS})"
            round_before = self._snapshot()

            notify(f"💻 Code Agent: Python 코드 생성 중... {tag}")
            self._store.update_status(session.id, SessionStatus.GENERATING)
            generated = self._code.generate_code(
                plan=plan, schema=schema, improvement_feedback=feedback
            )
            session.generated_code = generated
            notify(f"  └─ {len(generated.source_code.splitlines())}줄 생성 완료")

            notify(f"🔍 Validator: 코드 안전성 검증 중... {tag}")
            validation = validate_code(generated.source_code)
            if not validation.is_valid:
                return None, validation.error_message
            notify("  └─ 검증 통과")

            notify(f"🚀 Executor: 모델 학습 및 평가 중... {tag}")
            self._store.update_status(session.id, SessionStatus.RUNNING)
            exec_result = run_code(generated.source_code, df)
            if not exec_result.success:
                # 이미 성공한 라운드가 있으면 그 결과를 유지하고 종료
                if best_result is not None:
                    notify(f"  └─ ⚠️ 실행 오류 → 직전 성공 결과를 사용합니다: {exec_result.error_message}")
                    break
                # 아직 성공 결과가 없으면 오류를 피드백으로 재시도
                if i < self.MAX_IMPROVE_ROUNDS - 1:
                    notify(f"  └─ ⚠️ 실행 오류 → 개선 재시도: {exec_result.error_message}")
                    feedback = (
                        f"이전 코드가 실행 오류로 실패했습니다:\n{exec_result.error_message}\n"
                        "오류의 원인을 수정한 코드를 다시 작성하세요."
                    )
                    continue
                return None, exec_result.error_message

            metrics = exec_result.result or {}
            feature_importance = metrics.pop("feature_importance", None)
            result = AnalysisResult(
                id=str(uuid.uuid4()),
                session_id=session.id,
                metrics=metrics,
                feature_importance=feature_importance,
                generated_code=generated.source_code,
            )

            eval_out = None
            if self._eval:
                notify(f"🩺 결과 진단 중... {tag}")
                result.metrics["__feature_importance"] = feature_importance or {}
                eval_out = self._eval.evaluate(result)
                result.metrics["__eval"] = eval_out
                result.metrics.pop("__feature_importance", None)

            score = self._score(metrics, task_type)
            notify(f"  └─ 🔁 라운드 {i + 1} 성능: {self._score_label(metrics, task_type)}")
            self._notify_cost(notify, round_before, f"라운드 {i + 1} 비용")
            if best_score is None or (score is not None and score > best_score):
                best_score, best_result = score, result

            # 진단이 없으면(EvalAgent 미주입) 개선 방향을 정할 수 없으므로 종료
            if eval_out is None:
                break

            verdict = eval_out.get("verdict")
            if verdict == "신뢰 가능":
                notify("  └─ ✅ 진단 '신뢰 가능' — 개선 루프 종료")
                break

            if i < self.MAX_IMPROVE_ROUNDS - 1:
                feedback = self._format_feedback(eval_out, metrics, task_type)
                notify("  └─ 개선점을 반영해 다시 시도합니다...")

        if best_result is None:
            return None, "모델 학습에 실패했습니다."
        return best_result, None

    @staticmethod
    def _score(metrics: dict, task_type: str) -> Optional[float]:
        """성능 점수 (높을수록 좋음). 분류=f1(없으면 accuracy), 회귀=r2."""
        if task_type == "classification":
            return metrics.get("f1") or metrics.get("accuracy")
        return metrics.get("r2")

    @staticmethod
    def _score_label(metrics: dict, task_type: str) -> str:
        if task_type == "classification":
            acc, f1 = metrics.get("accuracy"), metrics.get("f1")
            parts = []
            if acc is not None:
                parts.append(f"정확도 {acc:.1%}")
            if f1 is not None:
                parts.append(f"F1 {f1:.3f}")
            return " · ".join(parts) or "측정값 없음"
        r2 = metrics.get("r2")
        return f"R² {r2:.4f}" if r2 is not None else "측정값 없음"

    @staticmethod
    def _format_feedback(eval_out: Optional[dict], metrics: dict, task_type: str) -> str:
        lines = [f"현재 성능: {Orchestrator._score_label(metrics, task_type)}"]
        if eval_out:
            lines.append(f"진단 판정: {eval_out.get('verdict', '')}")
            for c in eval_out.get("checks", []):
                if c.get("level") in ("warning", "critical"):
                    lines.append(f"- [{c['level']}] {c['item']}: {c['msg']}")
            for r in eval_out.get("recommendations", []):
                lines.append(f"- 개선 제안: {r}")
        lines.append(
            "위 문제를 개선하세요. 전처리 보강, 파생변수(feature engineering), "
            "알고리즘 변경, 하이퍼파라미터 조정 등을 활용해 성능을 높이세요."
        )
        return "\n".join(lines)

    # ──────────────────────────── Mode A ────────────────────────────

    def run_mode_a(
        self, request: ModeARequest, progress: Optional[ProgressCallback] = None
    ) -> OrchestratorResult:
        def notify(msg: str):
            if progress:
                progress(msg)

        session_id = str(uuid.uuid4())
        session = AnalysisSession(
            id=session_id,
            mode=SessionMode.A,
            status=SessionStatus.PENDING,
            natural_language_input=request.objective_text,
            csv_path=request.csv_path,
        )
        self._store.save(session)

        try:
            notify("📂 데이터 로드 중...")
            df = load_dataframe(request.csv_path)
            schema = infer_schema(df)
            session.schema = schema
            notify(f"  └─ {len(df):,}행 × {len(df.columns)}열 로드 완료")
            self._store.update_status(session_id, SessionStatus.PLANNING)

            total_before = self._snapshot()
            notify("📋 Plan Agent: 분석 계획 수립 중...")
            plan_before = self._snapshot()
            plan = self._plan.create_plan_mode_a(
                session_id=session_id,
                schema=schema,
                objective_text=request.objective_text,
                task_type=getattr(request, "task_type", "classification"),
            )
            session.plans = [plan]
            session.selected_plan = plan
            notify(f"  └─ [{plan.algorithm_family}] 알고리즘 선정")
            self._notify_cost(notify, plan_before, "계획 수립")

            result, err = self._run_improvement_loop(session, plan, schema, df, notify)
            if err:
                session.status = SessionStatus.FAILED
                session.error_message = err
                self._store.save(session)
                return OrchestratorResult(status="failed", session_id=session_id, error_message=err)

            cost = self._total_cost(total_before)
            if cost:
                result.metrics["__cost"] = cost
                notify(f"💰 총 비용: {_fmt_cost(cost['usd'])} (LLM 호출 누적)")
            session.result = result
            session.status = SessionStatus.COMPLETED
            self._store.save(session)

            notify("✅ 분석 완료!")
            return OrchestratorResult(
                status="completed",
                session_id=session_id,
                plans=[plan],
                result=result,
            )

        except Exception as e:
            session.status = SessionStatus.FAILED
            session.error_message = str(e)
            self._store.save(session)
            return OrchestratorResult(
                status="failed",
                session_id=session_id,
                error_message=str(e),
            )

    # ──────────────────────────── Mode B (Step 1) ───────────────────

    def propose_plans(
        self, request: ModeBRequest, progress: Optional[ProgressCallback] = None
    ) -> OrchestratorResult:
        def notify(msg: str):
            if progress:
                progress(msg)

        session_id = str(uuid.uuid4())
        from app.domain.models import DataSchema
        schema = DataSchema(columns=request.schema_columns, origin="USER_PROVIDED")

        session = AnalysisSession(
            id=session_id,
            mode=SessionMode.B,
            status=SessionStatus.PENDING,
            csv_path=request.csv_path,
            schema=schema,
        )
        self._store.save(session)

        try:
            notify("📋 Plan Agent: 분석 방향 3가지 탐색 중...")
            notify(f"  └─ {len(schema.columns)}개 컬럼 기반으로 전략 수립 중...")
            self._store.update_status(session_id, SessionStatus.PLANNING)
            plans = self._plan.propose_plans_mode_b(
                session_id=session_id,
                schema=schema,
                task_type=getattr(request, "task_type", "classification"),
                time_column=getattr(request, "time_column", None),
            )
            session.plans = plans
            session.status = SessionStatus.AWAITING_SELECTION
            self._store.save(session)

            for p in plans:
                notify(f"  └─ [{p.algorithm_family}] {p.title}")

            notify("💡 분석 방향 3가지 제안 완료. 하나를 선택하세요.")
            return OrchestratorResult(
                status="awaiting_selection",
                session_id=session_id,
                plans=plans,
            )

        except Exception as e:
            session.status = SessionStatus.FAILED
            session.error_message = str(e)
            self._store.save(session)
            return OrchestratorResult(
                status="failed",
                session_id=session_id,
                error_message=str(e),
            )

    # ──────────────────────────── Mode B (Step 2) ───────────────────

    def execute_selected_plan(
        self,
        session_id: str,
        plan_id: str,
        progress: Optional[ProgressCallback] = None,
    ) -> OrchestratorResult:
        def notify(msg: str):
            if progress:
                progress(msg)

        session = self._store.get(session_id)
        if not session:
            return OrchestratorResult(
                status="failed",
                session_id=session_id,
                error_message="세션을 찾을 수 없습니다.",
            )

        selected = next((p for p in session.plans if p.id == plan_id), None)
        if not selected:
            return OrchestratorResult(
                status="failed",
                session_id=session_id,
                error_message="선택한 계획을 찾을 수 없습니다.",
            )

        for p in session.plans:
            p.is_selected = p.id == plan_id
        session.selected_plan = selected

        try:
            notify("📂 데이터 로드 중...")
            df = load_dataframe(session.csv_path)
            notify(f"  └─ {len(df):,}행 × {len(df.columns)}열 로드 완료")

            total_before = self._snapshot()
            result, err = self._run_improvement_loop(session, selected, session.schema, df, notify)
            if err:
                session.status = SessionStatus.FAILED
                session.error_message = err
                self._store.save(session)
                return OrchestratorResult(status="failed", session_id=session_id, error_message=err)

            cost = self._total_cost(total_before)
            if cost:
                result.metrics["__cost"] = cost
                notify(f"💰 총 비용: {_fmt_cost(cost['usd'])} (LLM 호출 누적)")
            session.result = result
            session.status = SessionStatus.COMPLETED
            self._store.save(session)

            notify("✅ 분석 완료!")
            return OrchestratorResult(
                status="completed",
                session_id=session_id,
                plans=session.plans,
                result=result,
            )

        except Exception as e:
            session.status = SessionStatus.FAILED
            session.error_message = str(e)
            self._store.save(session)
            return OrchestratorResult(
                status="failed",
                session_id=session_id,
                error_message=str(e),
            )

    # ── Spec 자동 추출 ────────────────────────────────────────────────

    def parse_spec(self, column_names: list[str], spec_text: str) -> dict:
        """명세서 텍스트에서 컬럼 설명·타겟·분석유형을 추출한다.
        반환: {"task_type": str|None, "columns": {...}, "cost": {...}|None}"""
        if self._spec is None or not spec_text.strip():
            return {"task_type": None, "columns": {}, "cost": None}
        before = self._snapshot()
        result = self._spec.extract(column_names, mask_text(spec_text))
        result["cost"] = self._total_cost(before)
        return result

    # ── Chat ─────────────────────────────────────────────────────────

    def chat_about_result(
        self, result: AnalysisResult, history: list[dict]
    ) -> tuple[str, Optional[dict]]:
        """반환: (답변 텍스트, 비용 dict|None)."""
        if self._chat is None:
            return "채팅 에이전트가 초기화되지 않았습니다.", None
        before = self._snapshot()
        answer = self._chat.chat(result, history)
        return answer, self._total_cost(before)
