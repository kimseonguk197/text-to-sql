
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


# "tool 이름 : handler 함수" 매핑 (각 모듈의 HANDLERS를 모두 합함)
# {
#     "place_order":  _place_order함수,
#     "cancel_order": _cancel_order함수,
#     ...
# }
_TOOL_HANDLERS = {}
for module in CATEGORIES.values():   # order_tools, product_tools
    for name, handler in module.HANDLERS.items():
        _TOOL_HANDLERS[name] = handler


def execute_tool(tool_name: str, args: dict, db: Session, member_id: int) -> str:
    # tool 이름으로 handler 함수를 찾아 바로 실행
    handler = _TOOL_HANDLERS.get(tool_name)
    if not handler:
        raise ValueError(f"[registry] 등록되지 않은 tool: '{tool_name}'")
    return handler(args, db, member_id)
