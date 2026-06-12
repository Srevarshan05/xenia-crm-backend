from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.database import get_db
from app.models.promotion import Promotion
from app.models.product import Product
from app.models.customer import Customer, CustomerSegment
from app.schemas.promotions import PromotionCreate, PromotionUpdate, PromotionResponse

router = APIRouter(prefix="/api/promotions", tags=["Promotions"])

@router.get("/categories", response_model=List[str])
def get_promotion_categories(db: Session = Depends(get_db)):
    """
    GET /api/promotions/categories
    Retrieve distinct product categories available for promotion targeting.
    """
    categories = db.query(Product.category).distinct().filter(Product.category.isnot(None)).all()
    return sorted([c[0] for c in categories])

@router.get("/cities", response_model=List[str])
def get_promotion_cities(db: Session = Depends(get_db)):
    """
    GET /api/promotions/cities
    Retrieve distinct customer locations/cities available for promotion targeting.
    """
    cities = db.query(Customer.city).distinct().filter(Customer.city.isnot(None)).all()
    return sorted([c[0] for c in cities])

@router.get("/segments", response_model=List[str])
def get_promotion_segments(db: Session = Depends(get_db)):
    """
    GET /api/promotions/segments
    Retrieve distinct customer segments from the database for targeting, or default segments if empty.
    """
    segments = db.query(CustomerSegment.segment_name).distinct().filter(CustomerSegment.segment_name.isnot(None)).all()
    names = [s[0] for s in segments]
    default_segments = ["Champions", "Loyal Customers", "At Risk", "Lost Champions", "New Customers"]
    for d in default_segments:
        if d not in names:
            names.append(d)
    return sorted(names)

@router.get("", response_model=List[PromotionResponse])
def list_promotions(db: Session = Depends(get_db)):
    """
    GET /api/promotions
    Retrieve all promotions in the system.
    """
    return db.query(Promotion).order_by(Promotion.name).all()

@router.post("", response_model=PromotionResponse, status_code=status.HTTP_201_CREATED)
def create_promotion(payload: PromotionCreate, db: Session = Depends(get_db)):
    """
    POST /api/promotions
    Create a new promotion.
    """
    # Check if promo code already exists
    existing = db.query(Promotion).filter(Promotion.promo_code == payload.promo_code).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Promotion code '{payload.promo_code}' already exists."
        )

    # For backward compatibility with category and discount_percentage columns:
    # We populate 'category' with the first category or default, and 'discount_percentage' if discount_type is Percentage.
    category_val = payload.applicable_categories.split(",")[0] if payload.applicable_categories != "ALL" else None
    pct_val = payload.discount_value if payload.discount_type == "Percentage" else 0.00

    promotion = Promotion(
        name=payload.name,
        description=payload.description,
        promo_code=payload.promo_code,
        discount_type=payload.discount_type,
        discount_value=payload.discount_value,
        max_discount_cap=None,
        applicable_categories=payload.applicable_categories,
        applicable_cities=payload.applicable_cities,
        applicable_segments="ALL",
        start_date=payload.start_date,
        end_date=payload.end_date,
        max_usage_limit=None,
        per_shopper_limit=None,
        max_budget=None,
        min_order_value=None,
        active=payload.active,
        priority="Standard",
        allow_xenia_recommendations=True,
        category=category_val,
        discount_percentage=pct_val
    )
    
    db.add(promotion)
    db.commit()
    db.refresh(promotion)
    return promotion

@router.get("/{promotion_id}", response_model=PromotionResponse)
def get_promotion(promotion_id: UUID, db: Session = Depends(get_db)):
    """
    GET /api/promotions/{promotion_id}
    Retrieve details of a single promotion.
    """
    promotion = db.query(Promotion).filter(Promotion.promotion_id == promotion_id).first()
    if not promotion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Promotion not found."
        )
    return promotion

@router.put("/{promotion_id}", response_model=PromotionResponse)
def update_promotion(promotion_id: UUID, payload: PromotionUpdate, db: Session = Depends(get_db)):
    """
    PUT /api/promotions/{promotion_id}
    Update an existing promotion.
    """
    promotion = db.query(Promotion).filter(Promotion.promotion_id == promotion_id).first()
    if not promotion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Promotion not found."
        )

    # If updating promo code, make sure it is unique
    if payload.promo_code and payload.promo_code != promotion.promo_code:
        existing = db.query(Promotion).filter(Promotion.promo_code == payload.promo_code).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Promotion code '{payload.promo_code}' is already in use."
            )

    # Update fields
    update_data = payload.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(promotion, key, val)

    # Sync backward compatible fields if relevant
    if "applicable_categories" in update_data:
        promotion.category = promotion.applicable_categories.split(",")[0] if promotion.applicable_categories != "ALL" else None
    if "discount_value" in update_data or "discount_type" in update_data:
        promotion.discount_percentage = promotion.discount_value if promotion.discount_type == "Percentage" else 0.00

    db.commit()
    db.refresh(promotion)
    return promotion

@router.delete("/{promotion_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_promotion(promotion_id: UUID, db: Session = Depends(get_db)):
    """
    DELETE /api/promotions/{promotion_id}
    Delete a promotion from the database.
    """
    promotion = db.query(Promotion).filter(Promotion.promotion_id == promotion_id).first()
    if not promotion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Promotion not found."
        )
    
    db.delete(promotion)
    db.commit()
    return None

@router.patch("/{promotion_id}/status", response_model=PromotionResponse)
def toggle_promotion_status(promotion_id: UUID, db: Session = Depends(get_db)):
    """
    PATCH /api/promotions/{promotion_id}/status
    Toggle the active/inactive status of a promotion.
    """
    promotion = db.query(Promotion).filter(Promotion.promotion_id == promotion_id).first()
    if not promotion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Promotion not found."
        )
        
    promotion.active = not promotion.active
    db.commit()
    db.refresh(promotion)
    return promotion
