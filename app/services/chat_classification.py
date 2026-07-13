# 사용자 메시지의 의도를 3가지로 분류하여 각 파이프라인으로 라우팅
import os
from sqlalchemy.orm import Session
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.text_to_sql.sql_pipeline import call_sql_pipeline
from app.text_to_sql.llm_response import format_general_response
from app.tools.tool_pipeline import call_tool_pipeline

#  의도 분류 LLM. 
_llm_classify = ChatOpenAI(
    model="gpt-4.1-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0,  # 분류 목적의 낮은 temperature값 설정.
    max_tokens=10,  # QUERY / ACTION / GENERAL 등 적은 단어 수 필요
)

# 사용자 메시지 의도 분류: "QUERY" | "ACTION" | "GENERAL"
def classify_intent(user_message: str) -> str:
    prompt = ChatPromptTemplate.from_messages([
        ("system", """사용자의 메시지를 아래 3가지 중 하나로 분류하세요.
            QUERY: 데이터 조회/통계/검색 요청
                예) "나이 40살 이상 회원 목록", "내 주문 내역 보여줘", "카테고리별 상품 수"
            ACTION: 데이터 생성/변경/삭제 요청
                예) "상품 주문해줘", "새 상품 등록해줘", "주문 취소해줘", "재고 수정해줘"
            GENERAL: 그 외 일반 대화 (인사, 시스템 사용법, 기타)
                예) "안녕하세요", "이 앱은 뭐야?", "도움말"
            반드시 QUERY, ACTION, GENERAL 중 하나만 출력하세요."""),
        ("user", "{user_message}"),
    ])
    chain = prompt | _llm_classify | StrOutputParser()
    result = chain.invoke({"user_message": user_message})
    intent = result.strip().upper()

    if intent in ("QUERY", "ACTION", "GENERAL"):
        return intent

    # 예외: 예상치 못한 출력은 안전하게 QUERY로 처리
    print(f"[의도 분류] 예상치 못한 응답: '{result}' → QUERY로 fallback")
    return "QUERY"


# 사용자 메시지를 받아 의도에 맞는 파이프라인을 실행
def process_chat(
    user_message: str,
    db: Session,
    current_member_id: int,
) -> str:
    # 가장 먼저 사용자 메시지 분류작업
    intent = classify_intent(user_message)
    print(f"[파이프라인] 의도 분류 결과: {intent}")

    # 1)질의를 SQL로 변환(TEXT-TO-SQL)
    if intent == "QUERY":
        return call_sql_pipeline(user_message, db, current_member_id)
    # 2)기존API활용 작업(insert, update 등)
    elif intent == "ACTION":
        return call_tool_pipeline(user_message, db, current_member_id)
    # 3)DB 작업 없는 일반 LLM응답
    else:
        return format_general_response(user_message)
