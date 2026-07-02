"""
SQL 생성 (SQL Generation) : 자연어를 SQL로 변환하는 단계

<프롬프트 엔지니어링 전략>
  1. System Role     : "PostgreSQL 전문가" 역할 부여
  2. 스키마 주입      : DB 구조를 컨텍스트로 제공
  3. 규칙 명시        : 반드시 지켜야 할 제약 조건
  4. Few-shot 예시   : 좋은 SQL 예시 3개 제공 → 정확도 대폭 향상
  5. 출력 형식 지정   : SQL만 출력 (불필요한 설명 제거)
  6. 창의성이 아닌 정확성을 위해 temperature=0

"""

import os
import re
import logging
from langchain_openai import ChatOpenAI
# from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.text_to_sql.schema_context import get_schema_context

logger = logging.getLogger(__name__)

#  LLM 인스턴스 (SQL 생성 전용)
#  temperature=0: 재현 가능한 결정론적 SQL 생성
llm_sql = ChatOpenAI(
    model="gpt-4.1-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0,          # SQL은 창의성 불필요 → 0 고정
    max_tokens=1000,        # SQL이 지나치게 길어지는 것을 방지
)


#  Few-shot 예시 (SQL 생성 정확도를 높이는 핵심 기법)
#    1. 실제 사용 사례에서 자주 나오는 패턴을 선정
#    2. :current_member_id 사용 패턴을 반드시 포함
#    3. 날짜 함수, 집계 함수 예시 포함 (실수하기 쉬운 부분)
#    4. 단순 조회 → 집계 → JOIN → 복합 조건 순으로 난이도 배치
# ─────────────────────────────────────────────────────────────
FEW_SHOT_EXAMPLES = """
[예시 1 - 단순 조건 조회]
질문: 나이가 40살 이상인 회원 목록을 알려줘
SQL:
SELECT id, email, name, age, created_at
FROM members
WHERE age >= 40
ORDER BY age DESC
LIMIT 100;

[예시 2 - 개인 데이터 조회 (:current_member_id 필수)]
질문: 내가 주문한 상품 목록을 보여줘
SQL:
SELECT o.id, p.name AS product_name, p.category, p.price, o.quantity,
       (p.price * o.quantity) AS total_price, o.created_at
FROM orders o
JOIN products p ON o.product_id = p.id
WHERE o.member_id = :current_member_id
ORDER BY o.created_at DESC
LIMIT 100;

[예시 3 - 집계 함수 + 날짜 필터 + 개인 데이터]
질문: 내가 최근 1달 동안 주문한 총금액이 얼마야?
SQL:
SELECT SUM(p.price * o.quantity) AS total_amount
FROM orders o
JOIN products p ON o.product_id = p.id
WHERE o.member_id = :current_member_id
  AND o.created_at >= NOW() - INTERVAL '1 month';

[예시 4 - GROUP BY 집계]
질문: 카테고리별 상품 수와 평균 가격을 알려줘
SQL:
SELECT category,
       COUNT(*) AS product_count,
       ROUND(AVG(price)::NUMERIC, 0) AS avg_price
FROM products
GROUP BY category
ORDER BY product_count DESC
LIMIT 100;

[예시 5 - 복합 JOIN + 필터]
질문: 전자제품 카테고리에서 내가 구매한 총수량은?
SQL:
SELECT SUM(o.quantity) AS total_quantity
FROM orders o
JOIN products p ON o.product_id = p.id
WHERE o.member_id = :current_member_id
  AND p.category = '전자제품';
"""

# ─────────────────────────────────────────────────────────────
#  SQL 생성 프롬프트 템플릿
# ─────────────────────────────────────────────────────────────
SQL_GENERATION_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
"""사용자의 자연어 질문을 PostgreSQL SELECT 문으로 변환하세요.

## 데이터베이스 스키마
{schema}

## 반드시 지켜야 할 규칙
1. SELECT 문만 생성하세요.
2. 개인 데이터(orders, chats) 조회 시 WHERE member_id = :current_member_id 포함.
3. 집계 쿼리가 아닌 경우 LIMIT 100 포함.
4. SQL 코드만 출력하세요. 설명이나 마크다운 블록 없이.

## 참고 예시
{examples}

이제 아래 질문에 대한 SQL을 생성하세요.""",
    ),
    ("user", "{user_message}"),
])

#  SQL 수정 프롬프트 (자가 교정 / Self-Correction) : LLM이 잘못된 SQL을 생성했을 때, 오류 메시지를 다시 LLM에 전달해 스스로 수정하도록 요청하는 기법
SQL_FIX_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """아래 SQL 쿼리를 실행했을 때 오류가 발생했습니다. 오류를 분석하고 올바른 SQL로 수정하세요.

## 데이터베이스 스키마
{schema}

## 반드시 지켜야 할 규칙
1. SELECT 문만 생성하세요.
2. 개인 데이터(orders, chats) 조회 시 WHERE member_id = :current_member_id 포함.
3. 집계 쿼리가 아닌 경우 LIMIT 100 포함.
4. SQL 코드만 출력하세요. 설명이나 마크다운 블록 없이.

## 원본 SQL
{original_sql}

## 발생한 오류 메시지
{error_message}

위 오류를 수정한 올바른 SQL을 출력하세요.""",
    ),
    ("user", "수정된 SQL을 생성해주세요."),
])


# 자연어 질문을 PostgreSQL SELECT 문으로 변환
def generate_sql(user_message: str) -> str:
    schema = get_schema_context()
    chain = SQL_GENERATION_PROMPT | llm_sql | StrOutputParser()
    raw_sql = chain.invoke({
        "schema": schema,
        "examples": FEW_SHOT_EXAMPLES,
        "user_message": user_message,
    })

    # LLM이 가끔 마크다운 코드블록을 포함하는 경우 제거
    cleaned_sql = _strip_markdown_code_block(raw_sql)

    logger.debug(f"[SQL 생성] 입력: {user_message[:50]}... → SQL: {cleaned_sql[:100]}...")
    return cleaned_sql

# 실행 실패한 SQL을 LLM을 통해 자가 교정(Self-Correction)
def fix_sql(original_sql: str, error_message: str) -> str:
    schema = get_schema_context()
    chain = SQL_FIX_PROMPT | llm_sql | StrOutputParser()
    fixed_sql = chain.invoke({
        "schema": schema,
        "original_sql": original_sql,
        "error_message": error_message,
    })

    cleaned_sql = _strip_markdown_code_block(fixed_sql)
    logger.debug(f"[SQL 수정] 원본 오류: {error_message[:80]}... → 수정 SQL: {cleaned_sql[:100]}...")
    return cleaned_sql


def _strip_markdown_code_block(text: str) -> str:
    # ```sql ... ``` 또는 ``` ... ``` 패턴 제거
    text = re.sub(r"```(?:sql)?\s*\n?", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "")
    return text.strip()
