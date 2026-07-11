
## 핵심기능

- **회원(member)**: 회원가입(email, password, name, age) / 로그인(JWT 발급) / 마이페이지
- **상품(product)**: 등록(상품명, 카테고리, 가격, 재고) / 목록 검색 / 상세 조회
- **주문(order)**: 주문 생성(상품ID, 수량) / 주문 내역 조회
- **챗봇(chat)**: 자연어 질의/응답

## 실행 방법
### 1. 가상환경 생성 및 패키지 설치

```bash
python -m venv .venv
#가상환경모드
#window : .venv/Scripts/activate #비활성화는 deactivate
#mac : source .venv/bin/activate 
pip install -r requirements.txt
```

### 2. 서버 실행

```bash
uvicorn app.main:app --reload
```
