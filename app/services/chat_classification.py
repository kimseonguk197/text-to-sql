# 사용자 메시지의 의도를 3가지로 분류하여 각 파이프라인으로 라우팅
import os
import logging
from dataclasses import dataclass
from sqlalchemy.orm import Session
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.text_to_sql.sql_pipeline import call_sql_pipeline
from app.text_to_sql.llm_response import format_general_response
from app.tools.tool_pipeline import call_tool_pipeline

logger = logging.getLogger(__name__)

#  의도 분류 LLM & 프롬프트
_llm_classify = ChatOpenAI(
    model="gpt-4.1-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0,
    max_tokens=10,          # QUERY / ACTION / GENERAL 한 단어만 필요
)

_INTENT_CLASSIFICATION_PROMPT = ChatPromptTemplate.from_messages([
("system","""사용자의 메시지를 아래 3가지 중 하나로 분류하세요.
QUERY: 데이터 조회/통계/검색 요청
  예) "나이 40살 이상 회원 목록", "내 주문 내역 보여줘", "카테고리별 상품 수"
ACTION: 데이터 생성/변경/삭제 요청
  예) "상품 주문해줘", "새 상품 등록해줘", "주문 취소해줘", "재고 수정해줘"
GENERAL: 그 외 일반 대화 (인사, 시스템 사용법, 기타)
  예) "안녕하세요", "이 앱은 뭐야?", "도움말"
반드시 QUERY, ACTION, GENERAL 중 하나만 출력하세요.""",),
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



# 파이프라인 실행 결과
@dataclass
class ChatResult:
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
) -> ChatResult:
    # 의도 분류
    intent = classify_intent(user_message)
    logger.info(f"[파이프라인] 의도 분류 결과: {intent}")

    # 1)질의를 SQL로 변환(TEXT-TO-SQL)
    if intent == "QUERY":
        response = call_sql_pipeline(user_message, db, current_member_id)
    # 2)기존API활용 작업(insert, update 등)
    elif intent == "ACTION":
        response = call_tool_pipeline(user_message, db, current_member_id)
    # 3)DB 작업 없는 일반 LLM응답 
    else:
        response = format_general_response(user_message)

    return ChatResult(
        response=response,
        sql_used=None,
        row_count=0,
        retry_count=0,
        intent=intent,
    )
