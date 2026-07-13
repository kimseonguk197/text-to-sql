
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.dependencies import get_db, get_current_member
from app.services.chat_classification import process_chat

router = APIRouter(prefix="/chats", tags=["chat"])


@router.post(
    "",
    response_model=schemas.ChatResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_chat(
    body: schemas.ChatRequest,
    db: Session = Depends(get_db),
    current_member: models.Member = Depends(get_current_member),
):
    print(
        f"[채팅 API] 요청 | 회원ID={current_member.id} | "
        f"메시지={body.message[:60]}..."
    )

    # 매개변수 : 사용자질의문장, db세션, jwt토큰에서 추출한 사용자ID값 
    result = process_chat(
        user_message=body.message,
        db=db,
        current_member_id=current_member.id,
    )

    # 대화 이력 저장
    chat_record = models.Chat(
        member_id=current_member.id,
        request=body.message,
        response=result,
    )
    db.add(chat_record)
    db.commit()
    db.refresh(chat_record)

    return chat_record
