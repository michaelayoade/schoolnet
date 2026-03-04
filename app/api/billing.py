from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.schemas.billing import (
    CouponCreate,
    CouponRead,
    CouponUpdate,
    CustomerCreate,
    CustomerRead,
    CustomerUpdate,
    DiscountCreate,
    DiscountRead,
    EntitlementCreate,
    EntitlementRead,
    EntitlementUpdate,
    InvoiceCreate,
    InvoiceItemCreate,
    InvoiceItemRead,
    InvoiceItemUpdate,
    InvoiceRead,
    InvoiceUpdate,
    PaymentIntentCreate,
    PaymentIntentRead,
    PaymentIntentUpdate,
    PaymentMethodCreate,
    PaymentMethodRead,
    PaymentMethodUpdate,
    PriceCreate,
    PriceRead,
    PriceUpdate,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    SubscriptionCreate,
    SubscriptionItemCreate,
    SubscriptionItemRead,
    SubscriptionItemUpdate,
    SubscriptionRead,
    SubscriptionUpdate,
    UsageRecordCreate,
    UsageRecordRead,
    WebhookEventCreate,
    WebhookEventRead,
    WebhookEventUpdate,
)
from app.schemas.common import ListResponse
from app.services import billing as billing_service

router = APIRouter(tags=["billing"], dependencies=[Depends(require_role("admin"))])


# ── Products ─────────────────────────────────────────────


@router.post(
    "/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED
)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    try:
        item = billing_service.products.create(db, payload)
        db.commit()
        return item
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/products/{item_id}", response_model=ProductRead)
def get_product(item_id: str, db: Session = Depends(get_db)):
    try:
        return billing_service.products.get(db, item_id)
    except billing_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/products", response_model=ListResponse[ProductRead])
def list_products(
    is_active: bool | None = None,
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return billing_service.products.list_response(
            db, is_active, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/products/{item_id}", response_model=ProductRead)
def update_product(item_id: str, payload: ProductUpdate, db: Session = Depends(get_db)):
    try:
        item = billing_service.products.update(db, item_id, payload)
        db.commit()
        return item
    except billing_service.ProductNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/products/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(item_id: str, db: Session = Depends(get_db)) -> None:
    try:
        billing_service.products.delete(db, item_id)
        db.commit()
    except billing_service.ProductNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Prices ───────────────────────────────────────────────


@router.post("/prices", response_model=PriceRead, status_code=status.HTTP_201_CREATED)
def create_price(payload: PriceCreate, db: Session = Depends(get_db)):
    try:
        item = billing_service.prices.create(db, payload)
        db.commit()
        return item
    except billing_service.ProductNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/prices/{item_id}", response_model=PriceRead)
def get_price(item_id: str, db: Session = Depends(get_db)):
    try:
        return billing_service.prices.get(db, item_id)
    except billing_service.PriceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/prices", response_model=ListResponse[PriceRead])
def list_prices(
    product_id: str | None = None,
    type: str | None = None,
    currency: str | None = None,
    is_active: bool | None = None,
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return billing_service.prices.list_response(
            db,
            product_id,
            type,
            currency,
            is_active,
            order_by,
            order_dir,
            limit,
            offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/prices/{item_id}", response_model=PriceRead)
def update_price(item_id: str, payload: PriceUpdate, db: Session = Depends(get_db)):
    try:
        item = billing_service.prices.update(db, item_id, payload)
        db.commit()
        return item
    except billing_service.PriceNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/prices/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_price(item_id: str, db: Session = Depends(get_db)) -> None:
    try:
        billing_service.prices.delete(db, item_id)
        db.commit()
    except billing_service.PriceNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Customers ────────────────────────────────────────────


@router.post(
    "/customers", response_model=CustomerRead, status_code=status.HTTP_201_CREATED
)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)):
    try:
        item = billing_service.customers.create(db, payload)
        db.commit()
        return item
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/customers/{item_id}", response_model=CustomerRead)
def get_customer(item_id: str, db: Session = Depends(get_db)):
    try:
        return billing_service.customers.get(db, item_id)
    except billing_service.CustomerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/customers", response_model=ListResponse[CustomerRead])
def list_customers(
    person_id: str | None = None,
    email: str | None = None,
    is_active: bool | None = None,
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return billing_service.customers.list_response(
            db, person_id, email, is_active, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/customers/{item_id}", response_model=CustomerRead)
def update_customer(
    item_id: str, payload: CustomerUpdate, db: Session = Depends(get_db)
):
    try:
        item = billing_service.customers.update(db, item_id, payload)
        db.commit()
        return item
    except billing_service.CustomerNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/customers/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(item_id: str, db: Session = Depends(get_db)) -> None:
    try:
        billing_service.customers.delete(db, item_id)
        db.commit()
    except billing_service.CustomerNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Subscriptions ────────────────────────────────────────


@router.post(
    "/subscriptions",
    response_model=SubscriptionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_subscription(payload: SubscriptionCreate, db: Session = Depends(get_db)):
    try:
        item = billing_service.subscriptions.create(db, payload)
        db.commit()
        return item
    except billing_service.CustomerNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/subscriptions/{item_id}", response_model=SubscriptionRead)
def get_subscription(item_id: str, db: Session = Depends(get_db)):
    try:
        return billing_service.subscriptions.get(db, item_id)
    except billing_service.SubscriptionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/subscriptions", response_model=ListResponse[SubscriptionRead])
def list_subscriptions(
    customer_id: str | None = None,
    status: str | None = None,
    is_active: bool | None = None,
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return billing_service.subscriptions.list_response(
            db, customer_id, status, is_active, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/subscriptions/{item_id}", response_model=SubscriptionRead)
def update_subscription(
    item_id: str, payload: SubscriptionUpdate, db: Session = Depends(get_db)
):
    try:
        item = billing_service.subscriptions.update(db, item_id, payload)
        db.commit()
        return item
    except billing_service.SubscriptionNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/subscriptions/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subscription(item_id: str, db: Session = Depends(get_db)) -> None:
    try:
        billing_service.subscriptions.delete(db, item_id)
        db.commit()
    except billing_service.SubscriptionNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Subscription Items ───────────────────────────────────


@router.post(
    "/subscription-items",
    response_model=SubscriptionItemRead,
    status_code=status.HTTP_201_CREATED,
)
def create_subscription_item(
    payload: SubscriptionItemCreate, db: Session = Depends(get_db)
):
    try:
        item = billing_service.subscription_items.create(db, payload)
        db.commit()
        return item
    except (
        billing_service.SubscriptionNotFoundError,
        billing_service.PriceNotFoundError,
    ) as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/subscription-items/{item_id}", response_model=SubscriptionItemRead)
def get_subscription_item(item_id: str, db: Session = Depends(get_db)):
    try:
        return billing_service.subscription_items.get(db, item_id)
    except billing_service.SubscriptionItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/subscription-items", response_model=ListResponse[SubscriptionItemRead])
def list_subscription_items(
    subscription_id: str | None = None,
    price_id: str | None = None,
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return billing_service.subscription_items.list_response(
            db, subscription_id, price_id, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/subscription-items/{item_id}", response_model=SubscriptionItemRead)
def update_subscription_item(
    item_id: str, payload: SubscriptionItemUpdate, db: Session = Depends(get_db)
):
    try:
        item = billing_service.subscription_items.update(db, item_id, payload)
        db.commit()
        return item
    except billing_service.SubscriptionItemNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/subscription-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subscription_item(item_id: str, db: Session = Depends(get_db)) -> None:
    try:
        billing_service.subscription_items.delete(db, item_id)
        db.commit()
    except billing_service.SubscriptionItemNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Invoices ─────────────────────────────────────────────


@router.post(
    "/invoices", response_model=InvoiceRead, status_code=status.HTTP_201_CREATED
)
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db)):
    try:
        item = billing_service.invoices.create(db, payload)
        db.commit()
        return item
    except (
        billing_service.CustomerNotFoundError,
        billing_service.SubscriptionNotFoundError,
    ) as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/invoices/{item_id}", response_model=InvoiceRead)
def get_invoice(item_id: str, db: Session = Depends(get_db)):
    try:
        return billing_service.invoices.get(db, item_id)
    except billing_service.InvoiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/invoices", response_model=ListResponse[InvoiceRead])
def list_invoices(
    customer_id: str | None = None,
    subscription_id: str | None = None,
    status: str | None = None,
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return billing_service.invoices.list_response(
            db,
            customer_id,
            subscription_id,
            status,
            order_by,
            order_dir,
            limit,
            offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/invoices/{item_id}", response_model=InvoiceRead)
def update_invoice(item_id: str, payload: InvoiceUpdate, db: Session = Depends(get_db)):
    try:
        item = billing_service.invoices.update(db, item_id, payload)
        db.commit()
        return item
    except billing_service.InvoiceNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/invoices/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(item_id: str, db: Session = Depends(get_db)) -> None:
    try:
        billing_service.invoices.delete(db, item_id)
        db.commit()
    except billing_service.InvoiceNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Invoice Items ────────────────────────────────────────


@router.post(
    "/invoice-items",
    response_model=InvoiceItemRead,
    status_code=status.HTTP_201_CREATED,
)
def create_invoice_item(payload: InvoiceItemCreate, db: Session = Depends(get_db)):
    try:
        item = billing_service.invoice_items.create(db, payload)
        db.commit()
        return item
    except (
        billing_service.InvoiceNotFoundError,
        billing_service.PriceNotFoundError,
        billing_service.SubscriptionItemNotFoundError,
    ) as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/invoice-items/{item_id}", response_model=InvoiceItemRead)
def get_invoice_item(item_id: str, db: Session = Depends(get_db)):
    try:
        return billing_service.invoice_items.get(db, item_id)
    except billing_service.InvoiceItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/invoice-items", response_model=ListResponse[InvoiceItemRead])
def list_invoice_items(
    invoice_id: str | None = None,
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return billing_service.invoice_items.list_response(
            db, invoice_id, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/invoice-items/{item_id}", response_model=InvoiceItemRead)
def update_invoice_item(
    item_id: str, payload: InvoiceItemUpdate, db: Session = Depends(get_db)
):
    try:
        item = billing_service.invoice_items.update(db, item_id, payload)
        db.commit()
        return item
    except billing_service.InvoiceItemNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/invoice-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice_item(item_id: str, db: Session = Depends(get_db)) -> None:
    try:
        billing_service.invoice_items.delete(db, item_id)
        db.commit()
    except billing_service.InvoiceItemNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Payment Methods ──────────────────────────────────────


@router.post(
    "/payment-methods",
    response_model=PaymentMethodRead,
    status_code=status.HTTP_201_CREATED,
)
def create_payment_method(payload: PaymentMethodCreate, db: Session = Depends(get_db)):
    try:
        item = billing_service.payment_methods.create(db, payload)
        db.commit()
        return item
    except billing_service.CustomerNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/payment-methods/{item_id}", response_model=PaymentMethodRead)
def get_payment_method(item_id: str, db: Session = Depends(get_db)):
    try:
        return billing_service.payment_methods.get(db, item_id)
    except billing_service.PaymentMethodNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/payment-methods", response_model=ListResponse[PaymentMethodRead])
def list_payment_methods(
    customer_id: str | None = None,
    type: str | None = None,
    is_active: bool | None = None,
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return billing_service.payment_methods.list_response(
            db, customer_id, type, is_active, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/payment-methods/{item_id}", response_model=PaymentMethodRead)
def update_payment_method(
    item_id: str, payload: PaymentMethodUpdate, db: Session = Depends(get_db)
):
    try:
        item = billing_service.payment_methods.update(db, item_id, payload)
        db.commit()
        return item
    except billing_service.PaymentMethodNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/payment-methods/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_payment_method(item_id: str, db: Session = Depends(get_db)) -> None:
    try:
        billing_service.payment_methods.delete(db, item_id)
        db.commit()
    except billing_service.PaymentMethodNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Payment Intents ──────────────────────────────────────


@router.post(
    "/payment-intents",
    response_model=PaymentIntentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_payment_intent(payload: PaymentIntentCreate, db: Session = Depends(get_db)):
    try:
        item = billing_service.payment_intents.create(db, payload)
        db.commit()
        return item
    except (
        billing_service.CustomerNotFoundError,
        billing_service.InvoiceNotFoundError,
        billing_service.PaymentMethodNotFoundError,
    ) as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/payment-intents/{item_id}", response_model=PaymentIntentRead)
def get_payment_intent(item_id: str, db: Session = Depends(get_db)):
    try:
        return billing_service.payment_intents.get(db, item_id)
    except billing_service.PaymentIntentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/payment-intents", response_model=ListResponse[PaymentIntentRead])
def list_payment_intents(
    customer_id: str | None = None,
    invoice_id: str | None = None,
    status: str | None = None,
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return billing_service.payment_intents.list_response(
            db, customer_id, invoice_id, status, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/payment-intents/{item_id}", response_model=PaymentIntentRead)
def update_payment_intent(
    item_id: str, payload: PaymentIntentUpdate, db: Session = Depends(get_db)
):
    try:
        item = billing_service.payment_intents.update(db, item_id, payload)
        db.commit()
        return item
    except billing_service.PaymentIntentNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Usage Records ────────────────────────────────────────


@router.post(
    "/usage-records",
    response_model=UsageRecordRead,
    status_code=status.HTTP_201_CREATED,
)
def create_usage_record(payload: UsageRecordCreate, db: Session = Depends(get_db)):
    try:
        item = billing_service.usage_records.create(db, payload)
        db.commit()
        return item
    except billing_service.SubscriptionItemNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/usage-records/{item_id}", response_model=UsageRecordRead)
def get_usage_record(item_id: str, db: Session = Depends(get_db)):
    try:
        return billing_service.usage_records.get(db, item_id)
    except billing_service.UsageRecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/usage-records", response_model=ListResponse[UsageRecordRead])
def list_usage_records(
    subscription_item_id: str | None = None,
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return billing_service.usage_records.list_response(
            db, subscription_item_id, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Coupons ──────────────────────────────────────────────


@router.post("/coupons", response_model=CouponRead, status_code=status.HTTP_201_CREATED)
def create_coupon(payload: CouponCreate, db: Session = Depends(get_db)):
    try:
        item = billing_service.coupons.create(db, payload)
        db.commit()
        return item
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/coupons/{item_id}", response_model=CouponRead)
def get_coupon(item_id: str, db: Session = Depends(get_db)):
    try:
        return billing_service.coupons.get(db, item_id)
    except billing_service.CouponNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/coupons", response_model=ListResponse[CouponRead])
def list_coupons(
    valid: bool | None = None,
    code: str | None = None,
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return billing_service.coupons.list_response(
            db, valid, code, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/coupons/{item_id}", response_model=CouponRead)
def update_coupon(item_id: str, payload: CouponUpdate, db: Session = Depends(get_db)):
    try:
        item = billing_service.coupons.update(db, item_id, payload)
        db.commit()
        return item
    except billing_service.CouponNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/coupons/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_coupon(item_id: str, db: Session = Depends(get_db)) -> None:
    try:
        billing_service.coupons.delete(db, item_id)
        db.commit()
    except billing_service.CouponNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Discounts ────────────────────────────────────────────


@router.post(
    "/discounts", response_model=DiscountRead, status_code=status.HTTP_201_CREATED
)
def create_discount(payload: DiscountCreate, db: Session = Depends(get_db)):
    try:
        item = billing_service.discounts.create(db, payload)
        db.commit()
        return item
    except (
        billing_service.CouponNotFoundError,
        billing_service.CustomerNotFoundError,
        billing_service.SubscriptionNotFoundError,
    ) as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/discounts/{item_id}", response_model=DiscountRead)
def get_discount(item_id: str, db: Session = Depends(get_db)):
    try:
        return billing_service.discounts.get(db, item_id)
    except billing_service.DiscountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/discounts", response_model=ListResponse[DiscountRead])
def list_discounts(
    customer_id: str | None = None,
    subscription_id: str | None = None,
    coupon_id: str | None = None,
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return billing_service.discounts.list_response(
            db,
            customer_id,
            subscription_id,
            coupon_id,
            order_by,
            order_dir,
            limit,
            offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/discounts/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_discount(item_id: str, db: Session = Depends(get_db)) -> None:
    try:
        billing_service.discounts.delete(db, item_id)
        db.commit()
    except billing_service.DiscountNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Entitlements ─────────────────────────────────────────


@router.post(
    "/entitlements", response_model=EntitlementRead, status_code=status.HTTP_201_CREATED
)
def create_entitlement(payload: EntitlementCreate, db: Session = Depends(get_db)):
    try:
        item = billing_service.entitlements.create(db, payload)
        db.commit()
        return item
    except billing_service.ProductNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/entitlements/{item_id}", response_model=EntitlementRead)
def get_entitlement(item_id: str, db: Session = Depends(get_db)):
    try:
        return billing_service.entitlements.get(db, item_id)
    except billing_service.EntitlementNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/entitlements", response_model=ListResponse[EntitlementRead])
def list_entitlements(
    product_id: str | None = None,
    feature_key: str | None = None,
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return billing_service.entitlements.list_response(
            db, product_id, feature_key, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/entitlements/{item_id}", response_model=EntitlementRead)
def update_entitlement(
    item_id: str, payload: EntitlementUpdate, db: Session = Depends(get_db)
):
    try:
        item = billing_service.entitlements.update(db, item_id, payload)
        db.commit()
        return item
    except billing_service.EntitlementNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/entitlements/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entitlement(item_id: str, db: Session = Depends(get_db)) -> None:
    try:
        billing_service.entitlements.delete(db, item_id)
        db.commit()
    except billing_service.EntitlementNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Webhook Events ───────────────────────────────────────


@router.post(
    "/webhook-events",
    response_model=WebhookEventRead,
    status_code=status.HTTP_201_CREATED,
)
def create_webhook_event(payload: WebhookEventCreate, db: Session = Depends(get_db)):
    try:
        item = billing_service.webhook_events.create(db, payload)
        db.commit()
        return item
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/webhook-events/{item_id}", response_model=WebhookEventRead)
def get_webhook_event(item_id: str, db: Session = Depends(get_db)):
    try:
        return billing_service.webhook_events.get(db, item_id)
    except billing_service.WebhookEventNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/webhook-events", response_model=ListResponse[WebhookEventRead])
def list_webhook_events(
    provider: str | None = None,
    event_type: str | None = None,
    status: str | None = None,
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return billing_service.webhook_events.list_response(
            db, provider, event_type, status, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/webhook-events/{item_id}", response_model=WebhookEventRead)
def update_webhook_event(
    item_id: str, payload: WebhookEventUpdate, db: Session = Depends(get_db)
):
    try:
        item = billing_service.webhook_events.update(db, item_id, payload)
        db.commit()
        return item
    except billing_service.WebhookEventNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
