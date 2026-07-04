
import os
import json
import logging
from typing import Any
from langchain_openai import ChatOpenAI
# from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger(__name__)

#  SQL 조회후 응답 생성용 LLM
#  temperature=0.3: 약간의 자연스러움을 허용하되 일관성 유지
llm_format = ChatOpenAI(
    model="gpt-4.1-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0.3,
    max_tokens=1500,
)

#  SQL 조회없는 일반대화 응답 생성 LLM
#  temperature=0.5: 더 높은 자유도 부여
llm_chat = ChatOpenAI(
    model="gpt-4.1-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0.5,
    max_tokens=500,
)

# 결과를 LLM에 전달할 최대 행 수 : 이 이상이면 요약해서 전달
MAX_ROWS_FOR_LLM = 50

#  결과 포매팅 프롬프트
FORMAT_RESULT_PROMPT = ChatPromptTemplate.from_messages([
(
"system",
"""사용자의 질문에 대해 데이터베이스 조회 결과를 바탕으로 자연스러운 한국어로 답변하세요.
## 답변 규칙
1. 결과 데이터를 정확하게 반영해서 답변하세요.
2. 숫자는 가독성 있게 표현하세요. (예: 1500000 → 150만원, 1500000원)
3. 날짜는 YYYY-MM-DD 형식으로 표현하세요.
4. 결과가 여러 행이면 목록 형태로 정리하세요.
5. 결과가 없으면 "조회된 데이터가 없습니다."라고 친절하게 안내하세요.
6. 전체 결과가 {total_rows}건이고 {shown_rows}건만 보여주는 경우 그 사실을 언급하세요.
7. 불필요한 기술적 용어나 SQL 내용은 노출하지 마세요.
## 조회 결과 ({shown_rows}건)
{results}""",
    ),
    ("user", "{user_message}"),
])

# ─────────────────────────────────────────────────────────────
#  일반 대화 응답 프롬프트
# ─────────────────────────────────────────────────────────────
GENERAL_CHAT_PROMPT = ChatPromptTemplate.from_messages([
    (
"system",
"""
회원정보, 상품, 주문 데이터에 대한 질문에 답변할 수 있습니다.
데이터베이스 조회가 필요하지 않은 일반적인 대화에 자연스럽게 응답하세요.
답변은 간결하게 1-3문장 이내로 유지하세요.""",
    ),
    ("user", "{user_message}"),
])


# SQL 조회후 응답 생성용 LLM
def format_sql_result(
    user_message: str,
    query_results: list[dict[str, Any]],
) -> str:
    # ── 빈 결과 처리 ──────────────────────────────────────────
    if not query_results:
        return "조회된 데이터가 없습니다. 검색 조건을 다시 확인해 주세요."

    total_rows = len(query_results)

    # 결과 크기 제한 : 결과가 MAX_ROWS_FOR_LLM을 초과하면 앞부분만 전달
    truncated = query_results[:MAX_ROWS_FOR_LLM]
    shown_rows = len(truncated)

    # 결과를 JSON 형태로 직렬화하여 프롬프트에 포함
    results_json = json.dumps(truncated, ensure_ascii=False, indent=2)

    chain = FORMAT_RESULT_PROMPT | llm_format | StrOutputParser()
    response = chain.invoke({
        "user_message": user_message,
        "results": results_json,
        "total_rows": total_rows,
        "shown_rows": shown_rows,
    })

    logger.debug(f"[포매팅] {total_rows}건 결과를 자연어로 변환 완료")
    return response


# SQL 조회가 필요 없는 일반 대화에 응답 LLM
def format_general_response(user_message: str) -> str:
    chain = GENERAL_CHAT_PROMPT | llm_chat | StrOutputParser()
    return chain.invoke({"user_message": user_message})

# 모든 재시도 실패 후 사용자 친화적인 오류 메시지를 반환
def format_error_response(user_message: str, error_detail: str) -> str:
    logger.error(f"[포매팅] 오류 응답 생성 | 질문: {user_message[:50]} | 원인: {error_detail}")
    return (
        "죄송합니다. 요청하신 내용을 처리하는 중 문제가 발생했습니다. "
        "질문을 더 구체적으로 다시 입력해 주세요"
    )
