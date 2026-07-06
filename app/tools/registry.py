
from sqlalchemy.orm import Session

from app.tools import order_tools, product_tools

# 카테고리별 설명 (분류 프롬프트용) - 각 tool 모듈에 흩어져 있던 것을 이곳으로 통합
CATEGORY_DESCRIPTIONS: dict = {
    "order": "주문 생성, 주문 취소 등 주문관련",
    "product": "상품 등록, 상품 정보 수정 등 상품관련",
}

# 카테고리 이름과 설명을 "name: description" 형태의 문자열로 반환 (분류 프롬프트용)
def get_category_descriptions() -> str:
    lines = []
    for name, description in CATEGORY_DESCRIPTIONS.items():
        # "order: 주문 생성, 주문 취소 등 주문관련" 의 형태로 append
        lines.append(f"{name}: {description}")
    return "\n".join(lines)


#  카테고리 레지스트리 : dictionary에 파일자체를 매핑
CATEGORIES: dict = {
    "order": order_tools,
    "product": product_tools,
}
# 특정 카테고리의 TOOL_SCHEMAS만 반환
def get_schemas_by_category(category: str) -> list:
    return CATEGORIES[category].TOOL_SCHEMAS

# tool 이름 → 카테고리 모듈 매핑
# {
#     "create_order":  order_tools,   
#     "cancel_order":  order_tools,
#     ...
# }
_TOOL_NAME_TO_MODULE = {}
for module in CATEGORIES.values():          # order_tools, product_tools
    for tool in module.TOOL_SCHEMAS:        # 각 모듈의 tool 목록
        name = tool["function"]["name"]     # "create_order", "cancel_order" ...
        _TOOL_NAME_TO_MODULE[name] = module # 이름 → 모듈 매핑


def execute_tool(tool_name: str, args: dict, db: Session, member_id: int) -> str:
    # tool 이름으로 해당 카테고리 executor를 찾아 실행
    module = _TOOL_NAME_TO_MODULE.get(tool_name)
    if not module:
        raise ValueError(f"[registry] 등록되지 않은 tool: '{tool_name}'")
    # module은 order_tools 또는 product_tools (모듈 자체)을 의미
    # .execute은 그 모듈 안에 정의된 execute() 함수
    return module.execute(tool_name, args, db, member_id)
