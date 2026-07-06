
import logging
from sqlalchemy.orm import Session

from app.services import product_service

logger = logging.getLogger(__name__)

#  Tool 스키마 (OpenAI function calling 형식)
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "register_product",
            "description": "새로운 상품을 등록합니다. 사용자가 상품명, 카테고리, 가격, 재고 수량을 제공할 때 사용합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "등록할 상품명",
                    },
                    "category": {
                        "type": "string",
                        "description": "상품 카테고리 (예: 전자제품, 의류, 식품 등)",
                    },
                    "price": {
                        "type": "number",
                        "description": "상품 가격 (원 단위)",
                    },
                    "stock": {
                        "type": "integer",
                        "description": "초기 재고 수량",
                    },
                },
                "required": ["name", "category", "price", "stock"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_product",
            "description": "기존 상품 정보를 수정합니다. 상품명, 카테고리, 가격, 재고 중 변경할 항목만 지정합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "integer",
                        "description": "수정할 상품의 ID",
                    },
                    "name": {
                        "type": "string",
                        "description": "변경할 상품명 (선택)",
                    },
                    "category": {
                        "type": "string",
                        "description": "변경할 카테고리 (선택)",
                    },
                    "price": {
                        "type": "number",
                        "description": "변경할 가격 (선택)",
                    },
                    "stock": {
                        "type": "integer",
                        "description": "변경할 재고 수량 (선택)",
                    },
                },
                "required": ["product_id"],
            },
        },
    },
]


def execute(tool_name: str, args: dict, db: Session, member_id: int) -> str:
    """상품 카테고리 내 tool 이름으로 해당 함수 실행"""
    handlers = {
        "register_product": _register_product,
        "update_product": _update_product,
    }
    handler = handlers.get(tool_name)
    if not handler:
        raise ValueError(f"[product_tools] 알 수 없는 tool: {tool_name}")
    return handler(args, db, member_id)


#  개별 tool 구현
def _update_product(args: dict, db: Session, member_id: int) -> str:
    product_id: int = args["product_id"]
    fields = {k: v for k, v in args.items() if k != "product_id"}

    if not fields:
        return "변경할 항목이 없습니다. 수정할 필드를 지정해 주세요."

    try:
        product = product_service.update_product(db, member_id, product_id, **fields)
    except ValueError as e:
        return str(e)

    return (
        f"상품이 수정되었습니다!\n"
        f"- 상품 ID: {product.id}\n"
        f"- 상품명: {product.name}\n"
        f"- 카테고리: {product.category}\n"
        f"- 가격: {product.price:,.0f}원\n"
        f"- 재고: {product.stock}개"
    )


def _register_product(args: dict, db: Session, member_id: int) -> str:
    product = product_service.register_product(
        db, member_id, args["name"], args["category"], args["price"], args["stock"]
    )
    return (
        f"상품이 등록되었습니다!\n"
        f"- 상품 ID: {product.id}\n"
        f"- 상품명: {product.name}\n"
        f"- 카테고리: {product.category}\n"
        f"- 가격: {product.price:,.0f}원\n"
        f"- 재고: {product.stock}개"
    )
