from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.dependencies import get_db, get_current_member
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=schemas.OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    body: schemas.OrderCreate,
    db: Session = Depends(get_db),
    current_member: models.Member = Depends(get_current_member),
):
    try:
        order, _ = order_service.place_order(db, current_member.id, body.product_id, body.quantity)
        return order
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_member: models.Member = Depends(get_current_member),
):
    try:
        order_service.cancel_order(db, current_member.id, order_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/me", response_model=List[schemas.OrderResponse])
def my_orders(
    db: Session = Depends(get_db),
    current_member: models.Member = Depends(get_current_member),
):
    return db.query(models.Order).filter(
        models.Order.member_id == current_member.id,
        models.Order.del_yn == 'N',
    ).all()
