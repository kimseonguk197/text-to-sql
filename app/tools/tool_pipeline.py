
import os
import logging
from sqlalchemy.orm import Session
from langchain_openai import ChatOpenAI

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.tools.registry import get_category_descriptions, get_schemas_by_category, execute_tool, CATEGORIES

logger = logging.getLogger(__name__)

# 1단계: 카테고리 분류용 LLM
# 파라미터 추출은 창의성 불필요하므로, temperature=0. 카테고리 이름만 출력하면 되므로 max_tokens 최소화
_llm_classify = ChatOpenAI(
    model="gpt-4.1-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0,
    max_tokens=20,
)

# 2단계: tool 선택 및 파라미터 추출용 LLM
_llm = ChatOpenAI(
    model="gpt-4.1-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0,
)

# 카테고리만 분류 : 카테고리 이름과 설명을 LLM에 전달
def _classify_category(user_message: str) -> str:
    
    prompt = ChatPromptTemplate.from_messages([
    ("system",
        """사용자의 요청이 아래 카테고리 중 어디에 해당하는지 분류하세요.
        {category_descriptions}
        반드시 카테고리 이름만 출력하세요.""",),
    ("user", "{user_message}"),
    ])
    chain = prompt | _llm_classify | StrOutputParser()
    result = chain.invoke({
        # 카테고리 : order, product 등
        "category_descriptions": get_category_descriptions(),
        "user_message": user_message,
    })
    category = result.strip().lower()
    if category not in CATEGORIES:
        logger.warning(f"[tool_pipeline] 알 수 없는 카테고리: '{category}' → 전체 fallback")
        return None
    logger.info(f"[tool_pipeline] 카테고리 분류: {category}")
    return category


# 사용자 메시지로부터 적절한 tool(api)을 선택하고 실행
def call_tool_pipeline(user_message: str, db: Session, member_id: int) -> str:
    # 1.함수 카테고리 분류(주문, 상품 등)
    category = _classify_category(user_message)
    if category is None:
        return "처리할 수 없는 요청입니다."

    # 2.분류된 카테고리의 함수 가져오기(place_order 인지, cancel_order인지)
    tools = get_schemas_by_category(category)
    llm_with_tools = _llm.bind_tools(tools)
    prompt = ChatPromptTemplate.from_messages([
        ("system", """당신은 사용자의 요청을 분석하여 적절한 함수를 호출하는 도우미입니다.
                    사용자의 요청에서 필요한 정보를 추출하여 함수를 호출하세요.
                    함수 호출에 필요한 파라미터가 불명확한 경우, tool을 호출하지 말고 어떤 정보가 필요한지 안내하세요."""),
        ("user", "{user_message}"),
    ])
    chain = prompt | llm_with_tools
    response = chain.invoke({"user_message": user_message})
    print(response)
    # 3.LLM이 함수명(tool)을 선택하지 않은 경우 (파라미터 부족 등)
    if not response.tool_calls:
        logger.info("[tool_pipeline] tool 미선택 → LLM 직접 응답 반환")
        return response.content or "요청을 처리하려면 더 구체적인 정보가 필요합니다."

    tool_call = response.tool_calls[0]
    tool_name = tool_call["name"]
    args = tool_call["args"]

    logger.info(f"[tool_pipeline] 실행 | tool={tool_name} | args={args}")

    try:
        return execute_tool(tool_name, args, db, member_id)
    except Exception as e:
        logger.error(f"[tool_pipeline] 실행 실패 | tool={tool_name} | error={e}")
        return f"요청 처리 중 오류가 발생했습니다: {str(e)}"
