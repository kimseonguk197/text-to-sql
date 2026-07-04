"""
사용자 메시지의 의도를 3가지로 분류하여 각 파이프라인으로 라우팅

사용자 메시지
    │
    ▼
의도 분류 (QUERY / ACTION / GENERAL)
    │
    ├── GENERAL → 일반 대화 응답 (LLM 직접 응답)
    │
    ├── ACTION  → Function Calling 파이프라인 -> 기존 API호출
    │
    └── QUERY   → Text-to-SQL 파이프라인 : SQL 생성 → 검증 → 실행 → 포매팅
"""

import os
import logging
from dataclasses import dataclass
from sqlalchemy.orm import Session
from langchain_openai import ChatOpenAI
# from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.text_to_sql.sql_generator import generate_sql, fix_sql
from app.text_to_sql.sql_validator import validate_and_sanitize
from app.text_to_sql.sql_executor import execute_sql
from app.text_to_sql.llm_response import (
    format_sql_result,
    format_general_response,
    format_error_response,
)
from app.tools.tool_caller import call_tool

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  의도 분류 LLM & 프롬프트
# ─────────────────────────────────────────────────────────────
_llm_classify = ChatOpenAI(
    model="gpt-4.1-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0,
    max_tokens=10,          # QUERY / ACTION / GENERAL 한 단어만 필요
)

_INTENT_CLASSIFICATION_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """사용자의 메시지를 아래 3가지 중 하나로 분류하세요.

QUERY: 데이터 조회/통계/검색 요청
  예) "나이 40살 이상 회원 목록", "내 주문 내역 보여줘", "카테고리별 상품 수"

ACTION: 데이터 생성/변경/삭제 요청
  예) "상품 주문해줘", "새 상품 등록해줘", "주문 취소해줘", "재고 수정해줘"

GENERAL: 일반 대화 (인사, 시스템 사용법, 기타)
  예) "안녕하세요", "이 앱은 뭐야?", "도움말"

반드시 QUERY, ACTION, GENERAL 중 하나만 출력하세요.""",
    ),
    ("user", "{user_message}"),
])


# 사용자 메시지 의도 분류: "QUERY" | "ACTION" | "GENERAL"
def classify_intent(user_message: str) -> str:
    chain = _INTENT_CLASSIFICATION_PROMPT | _llm_classify | StrOutputParser()
    result = chain.invoke({"user_message": user_message})
    intent = result.strip().upper()

    if intent in ("QUERY", "ACTION", "GENERAL"):
        return intent

    # 예외: 예상치 못한 출력은 안전하게 QUERY로 처리
    logger.warning(f"[의도 분류] 예상치 못한 응답: '{result}' → QUERY로 fallback")
    return "QUERY"


#  Self-Correction 최대 재시도 횟수
MAX_RETRY_COUNT = 3


# 파이프라인 실행 결과
@dataclass
class TextToSQLResult:
    response: str            # 사용자에게 보여줄 최종 응답
    sql_used: str | None     # 실행된 SQL (QUERY 경로만 존재, 디버깅용)
    row_count: int           # 조회된 행 수 (QUERY 경로만 의미 있음)
    retry_count: int         # 재시도 횟수 (0 = 첫 번째 시도 성공)
    intent: str              # 처리된 의도: "QUERY" | "ACTION" | "GENERAL"

# 사용자 메시지를 받아 의도에 맞는 파이프라인을 실행
def process_chat(
    user_message: str,
    db: Session,
    current_member_id: int,
) -> TextToSQLResult:


    # ── Step 1: 의도 분류 ─────────────────────────────────────
    intent = classify_intent(user_message)
    logger.info(f"[파이프라인] 의도 분류 결과: {intent}")

    # 1)GENERAL: 일반 대화
    if intent == "GENERAL":
        logger.info("[파이프라인] GENERAL → LLM 직접 응답")
        response = format_general_response(user_message)
        return TextToSQLResult(
            response=response,
            sql_used=None,
            row_count=0,
            retry_count=0,
            intent="GENERAL",
        )

    # 2) ACTION: 기존api활용 
    if intent == "ACTION":
        logger.info("[파이프라인] ACTION → Function Calling 파이프라인")
        response = call_tool(user_message, db, current_member_id)
        return TextToSQLResult(
            response=response,
            sql_used=None,
            row_count=0,
            retry_count=0,
            intent="ACTION",
        )
    # 3) Text-to-SQL: 질의에 따른 SQL 생성 및 실행
    return _run_text_to_sql(user_message, db, current_member_id)

# SQL 생성 → 검증 → 실행을 최대 MAX_RETRY_COUNT 회 재시도
def _run_text_to_sql(
    user_message: str,
    db: Session,
    current_member_id: int,
) -> TextToSQLResult:
    current_sql = ""
    last_error = ""
    retry_count = 0

    for attempt in range(MAX_RETRY_COUNT):
        # ── SQL 생성 또는 수정 ────────────────────────────────
        if attempt == 0:
            logger.info(f"[Text-to-SQL] SQL 생성 시도 #{attempt + 1}")
            current_sql = generate_sql(user_message)
        else:
            # 이전 오류를 기반으로 SQL 수정 (Self-Correction)
            logger.info(
                f"[Text-to-SQL] SQL 수정 시도 #{attempt + 1} | "
                f"이전 오류: {last_error[:60]}..."
            )
            current_sql = fix_sql(current_sql, last_error)
            retry_count = attempt

        # ── SQL 검증 ──────────────────────────────────────────
        validation = validate_and_sanitize(current_sql, requires_rls=True)

        if not validation.is_valid:
            # RLS 위반 중 타인 데이터 접근 시도 → Self-Correction 없이 즉시 차단
            if validation.is_unauthorized:
                logger.warning("[Text-to-SQL] 타인 데이터 접근 시도 감지 → 즉시 차단")
                return TextToSQLResult(
                    response="다른 사용자의 데이터는 조회할 수 없습니다.",
                    sql_used=None,
                    row_count=0,
                    retry_count=0,
                    intent="QUERY",
                )
            last_error = str(validation)
            continue

        # ── SQL 실행 ──────────────────────────────────────────
        execution_params = {
            "current_member_id": current_member_id,
            # 필요에 따라 추가 파라미터 확장 가능
            # 예: "today": datetime.now(timezone.utc).date()
        }

        try:
            sanitized_sql = validation.sanitized_sql
            results = execute_sql(db, sanitized_sql, execution_params)

            logger.info(
                f"[Text-to-SQL] 성공 | {len(results)}건 조회 | 재시도={retry_count}회"
            )
            response_text = format_sql_result(user_message, results)

            return TextToSQLResult(
                response=response_text,
                sql_used=sanitized_sql,
                row_count=len(results),
                retry_count=retry_count,
                intent="QUERY",
            )

        except Exception as e:
            # SQL 실행 실패 → 오류 메시지를 다음 재시도에 전달
            last_error = str(e)
            logger.warning(
                f"[Text-to-SQL] 실행 실패 (시도 #{attempt + 1}): {last_error}"
            )
            continue

    # 모든 재시도 실패
    error_response = format_error_response(user_message, last_error)

    return TextToSQLResult(
        response=error_response,
        sql_used=current_sql,    # 디버깅을 위해 마지막 SQL 포함
        row_count=0,
        retry_count=MAX_RETRY_COUNT,
        intent="QUERY",
    )
