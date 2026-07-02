"""
스키마 컨텍스트 (Schema Context)
📌 LLM 프롬프트에 DB 구조를 주입해 LLM이 올바른 SQL을 생성할 수 있도록 돕는 기법

📌 제공 방식
- 방법1 : DDL 방식(CREATE TABLE 문 그대로 제공)
- 방법2 : 자연어 방식(테이블 구조를 자연어로 설명)
- 방법3 : 하이브리드 방식( DDL + 자연어 설명 혼합) -> 우리 수업의 방식

📌 보안설계
  - password 등 민감 컬럼은 스키마에서 제외
  - LLM이 해당 컬럼을 모르면 SELECT에 포함시킬수 없음

📌 고도화
  - 테이블의 규모가 커질때 "동적 스키마 선택(Dynamic Schema Selection)"도입
"""

#  데이터베이스 스키마 (DDL + 자연어 설명 하이브리드)
DATABASE_SCHEMA = """
-- [members] 회원 테이블 : 서비스를 이용하는 사용자 정보를 저장
CREATE TABLE members (
    id          INTEGER     PRIMARY KEY,
    email       VARCHAR     NOT NULL,       -- 이메일 (로그인 ID)
    name        VARCHAR,                    -- 회원 이름
    age         INTEGER,                    -- 나이
    created_at  TIMESTAMP                   -- 가입 일시 (UTC)
);

-- [products] 상품 테이블 : 판매 중인 상품 목록
CREATE TABLE products (
    id          INTEGER     PRIMARY KEY,
    name        VARCHAR     NOT NULL,       -- 상품명
    category    VARCHAR     NOT NULL,       -- 카테고리 (예: 전자제품, 의류, 식품)
    price       FLOAT       NOT NULL,       -- 상품 가격 (원 단위)
    stock       INTEGER     NOT NULL,       -- 현재 재고 수량
    member_id   INTEGER,                    -- 상품 등록자 회원 ID (FK → members.id)
    created_at  TIMESTAMP                   -- 등록 일시 (UTC)
);

-- [orders] 주문 테이블 : 회원의 상품 구매 이력
CREATE TABLE orders (
    id          INTEGER     PRIMARY KEY,
    member_id   INTEGER     NOT NULL,       -- 주문한 회원 ID (FK → members.id)
    product_id  INTEGER     NOT NULL,       -- 주문한 상품 ID (FK → products.id)
    quantity    INTEGER     NOT NULL,       -- 주문 수량
    created_at  TIMESTAMP                   -- 주문 일시 (UTC)
);

-- [chats] 채팅 이력 테이블 : 챗봇과의 대화 내용을 저장
CREATE TABLE chats (
    id          INTEGER     PRIMARY KEY,
    member_id   INTEGER     NOT NULL,       -- 질의한 회원 ID (FK → members.id)
    request     VARCHAR     NOT NULL,       -- 사용자 질문
    response    VARCHAR     NOT NULL,       -- AI 응답
    created_at  TIMESTAMP                   -- 질의 일시 (UTC)
);
"""

#  테이블 관계 설명
TABLE_RELATIONSHIPS = """
[테이블 관계]
- members(id) ↔ orders(member_id)   : 1:N — 한 회원이 여러 주문 가능
- products(id) ↔ orders(product_id) : 1:N — 한 상품이 여러 주문에 포함 가능
- members(id) ↔ products(member_id) : 1:N — 한 회원이 여러 상품 등록 가능
- members(id) ↔ chats(member_id)    : 1:N — 한 회원이 여러 채팅 가능
"""

#  보안 정책: 허용된 테이블 화이트리스트 : SQL 검증 단계에서 이 목록에 없는 테이블 접근을 차단
ALLOWED_TABLES = frozenset({"members", "products", "orders", "chats"})

#  보안 정책: Row(행)-Level Security (RLS) 대상 테이블
#  이 테이블을 사용하는 쿼리는 반드시 현재 로그인 회원의 데이터만 조회하도록 member_id 필터가 자동 적용
PERSONAL_TABLES = frozenset({"orders", "chats"})

#  LLM에 주입할 전체 스키마 컨텍스트를 반환
def get_schema_context() -> str:
    return DATABASE_SCHEMA.strip() + "\n\n" + TABLE_RELATIONSHIPS.strip()


# ──────────────────────────────────────────────────────────────────────────────
#  동적 스키마 선택 (Dynamic Schema Selection)
#
#  📌 왜 필요한가?
#    테이블이 수십~수백 개인 실제 서비스에서 전체 스키마를 매번 주입하면:
#    1. 토큰 비용 폭증  : 스키마만으로 수천~수만 토큰 소비
#    2. 정확도 하락     : 관련 없는 테이블이 많을수록 LLM이 혼동
#    3. 컨텍스트 창 초과: GPT-4의 최대 컨텍스트 초과 가능
#
#    → 쿼리와 관련된 테이블만 선택적으로 주입하면 이 세 문제를 동시에 해결합니다.
#
#  📌 FK 의존성 자동 확장
#    "orders 테이블만 알려줘" 라고 해도 JOIN을 위해
#    members, products 테이블 DDL도 함께 포함해야 합니다.
#    → FK 의존성 그래프를 순회해 자동으로 필요한 테이블을 추가합니다.
#
#  📌 실제 활용 패턴 (이 예제에서는 구현 생략, 확장 가능)
#    1단계: LLM으로 사용자 질문에서 언급된 테이블명을 먼저 추출
#    2단계: get_schema_context_dynamic(추출된 테이블들) 호출
#    3단계: 동적 스키마로 SQL 생성
# ──────────────────────────────────────────────────────────────────────────────

# 테이블별 DDL 조각 (동적 선택을 위해 테이블 단위로 분리)
_TABLE_DDL: dict[str, str] = {
    "members": """\
-- [members] 회원 테이블 : 서비스를 이용하는 사용자 정보를 저장
CREATE TABLE members (
    id          INTEGER     PRIMARY KEY,
    email       VARCHAR     NOT NULL,
    name        VARCHAR,
    age         INTEGER,
    created_at  TIMESTAMP
);""",
    "products": """\
-- [products] 상품 테이블 : 판매 중인 상품 목록
CREATE TABLE products (
    id          INTEGER     PRIMARY KEY,
    name        VARCHAR     NOT NULL,
    category    VARCHAR     NOT NULL,
    price       FLOAT       NOT NULL,
    stock       INTEGER     NOT NULL,
    member_id   INTEGER,                    -- FK → members.id
    created_at  TIMESTAMP
);""",
    "orders": """\
-- [orders] 주문 테이블 : 회원의 상품 구매 이력
CREATE TABLE orders (
    id          INTEGER     PRIMARY KEY,
    member_id   INTEGER     NOT NULL,       -- FK → members.id
    product_id  INTEGER     NOT NULL,       -- FK → products.id
    quantity    INTEGER     NOT NULL,
    created_at  TIMESTAMP
);""",
    "chats": """\
-- [chats] 채팅 이력 테이블 : 챗봇과의 대화 내용을 저장
CREATE TABLE chats (
    id          INTEGER     PRIMARY KEY,
    member_id   INTEGER     NOT NULL,       -- FK → members.id
    request     VARCHAR     NOT NULL,
    response    VARCHAR     NOT NULL,
    created_at  TIMESTAMP
);""",
}

# FK 의존성 그래프: 특정 테이블을 조회할 때 JOIN에 필요한 테이블 목록
# 예) orders를 조회하면 members(주문자 정보)와 products(상품 정보) DDL도 필요
_FK_DEPENDENCIES: dict[str, frozenset[str]] = {
    "members":  frozenset(),
    "products": frozenset({"members"}),
    "orders":   frozenset({"members", "products"}),
    "chats":    frozenset({"members"}),
}

# 관계 설명 조각: (테이블A, 테이블B, 설명)
# 두 테이블이 모두 선택된 경우에만 해당 관계를 출력합니다.
_RELATIONSHIP_LINES: list[tuple[str, str, str]] = [
    ("members",  "orders",   "- members(id) ↔ orders(member_id)   : 1:N — 한 회원이 여러 주문 가능"),
    ("products", "orders",   "- products(id) ↔ orders(product_id) : 1:N — 한 상품이 여러 주문에 포함 가능"),
    ("members",  "products", "- members(id) ↔ products(member_id) : 1:N — 한 회원이 여러 상품 등록 가능"),
    ("members",  "chats",    "- members(id) ↔ chats(member_id)    : 1:N — 한 회원이 여러 채팅 가능"),
]

# DDL 출력 순서 (의존되는 테이블이 먼저 오도록)
_TABLE_ORDER = ["members", "products", "orders", "chats"]


def get_schema_context_dynamic(relevant_tables: list[str]) -> str:
    """
    쿼리에서 언급된 테이블만 포함한 최소화된 스키마 컨텍스트를 반환합니다.
    FK로 연결된 의존 테이블은 자동으로 함께 포함됩니다.

    Args:
        relevant_tables: 포함할 테이블명 목록
                         예: ["orders"] → orders + members + products 자동 포함

    Returns:
        선택된 테이블의 DDL + 해당 테이블 간 관계 설명

    사용 예:
        # "내 주문 내역 조회" → orders 테이블 관련
        ctx = get_schema_context_dynamic(["orders"])

        # "상품 목록과 회원 정보" → 두 테이블 지정
        ctx = get_schema_context_dynamic(["products", "members"])

        # 빈 리스트 → 안전망으로 전체 스키마 반환
        ctx = get_schema_context_dynamic([])
    """
    # ── Step 1. 입력 정규화 + 화이트리스트 필터 ───────────────
    # 소문자 변환 후 허용 목록에 없는 테이블명은 조용히 제외합니다.
    # (잘못된 테이블명 입력에 대한 안전 처리)
    normalized: set[str] = {t.lower().strip() for t in relevant_tables} & ALLOWED_TABLES

    if not normalized:
        # 유효한 테이블이 하나도 없으면 전체 스키마 반환 (안전망)
        return get_schema_context()

    # ── Step 2. FK 의존성 확장 ────────────────────────────────
    # 요청 테이블의 FK가 참조하는 테이블을 재귀적으로 포함합니다.
    #
    # 예) relevant_tables = ["orders"]
    #   → orders의 FK 의존성: {members, products}
    #   → 최종 포함: {orders, members, products}
    #
    # 현재 스키마는 깊이가 1이라 단순 합집합으로 충분합니다.
    # 의존 관계가 깊어지면 BFS/DFS 탐색으로 확장하세요.
    expanded: set[str] = set(normalized)
    for table in normalized:
        expanded |= _FK_DEPENDENCIES.get(table, frozenset())

    # ── Step 3. DDL 조립 (의존 순서 보장) ────────────────────
    # 참조되는 테이블(members)이 참조하는 테이블(orders)보다 먼저 나오도록
    # _TABLE_ORDER 순서로 출력합니다.
    ddl_parts = [
        _TABLE_DDL[table]
        for table in _TABLE_ORDER
        if table in expanded
    ]

    # ── Step 4. 관련 관계 설명만 필터링 ─────────────────────
    # 양쪽 테이블이 모두 expanded에 포함된 경우에만 관계를 출력합니다.
    rel_lines = [
        line
        for t1, t2, line in _RELATIONSHIP_LINES
        if t1 in expanded and t2 in expanded
    ]

    # ── Step 5. 최종 컨텍스트 조립 ───────────────────────────
    schema_section = "\n\n".join(ddl_parts)
    rel_section = "[테이블 관계]\n" + "\n".join(rel_lines) if rel_lines else ""

    return (schema_section + ("\n\n" + rel_section if rel_section else "")).strip()
