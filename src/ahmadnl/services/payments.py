from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ahmadnl.models import Order, OrderStatus, PaymentRecord, PaymentStatus, Product, ProductPrice
from ahmadnl.services.credits import grant


class PaymentBoundaryError(RuntimeError):
    pass


async def create_order(session: AsyncSession, user_id: str, product_id: str, price_id: str) -> Order:
    product = await session.get(Product, product_id)
    price = await session.get(ProductPrice, price_id)
    if not product or not price or price.product_id != product.id or not product.active:
        raise PaymentBoundaryError("Product is not available.")
    order = Order(user_id=user_id, product_id=product.id, price_id=price.id, status=OrderStatus.CREATED)
    session.add(order)
    await session.flush()
    session.add(PaymentRecord(order_id=order.id, provider=price.provider, status=PaymentStatus.PENDING, amount=price.amount, currency=price.currency))
    return order


async def verify_order_for_checkout(session: AsyncSession, order_id: str, currency: str, amount: int) -> bool:
    order = await session.get(Order, order_id)
    if not order or order.status != OrderStatus.CREATED:
        return False
    price = await session.get(ProductPrice, order.price_id)
    product = await session.get(Product, order.product_id)
    return bool(product and product.active and price and price.currency == currency and price.amount == amount)


async def complete_successful_payment(
    session: AsyncSession,
    *,
    order_id: str,
    provider_payment_id: str,
    currency: str,
    amount: int,
    expected_user_id: str,
) -> Order:
    order = await session.get(Order, order_id)
    if not order or order.user_id != expected_user_id:
        raise PaymentBoundaryError("Order not found.")
    if order.status == OrderStatus.PAID:
        return order
    if not await verify_order_for_checkout(session, order_id, currency, amount):
        order.status = OrderStatus.FAILED
        payment = await _payment_for_order(session, order.id)
        if payment:
            payment.status = PaymentStatus.FAILED
        return order

    product = await session.get(Product, order.product_id)
    payment = await _payment_for_order(session, order.id)
    order.status = OrderStatus.PAID
    if payment:
        payment.status = PaymentStatus.SUCCEEDED
        payment.provider_payment_id = provider_payment_id
    await grant(session, order.user_id, product.credits, f"order-paid:{order.id}", "Telegram Stars purchase")
    return order


async def mark_development_paid(session: AsyncSession, order_id: str) -> None:
    order = await session.get(Order, order_id)
    if not order:
        raise PaymentBoundaryError("Order not found.")
    if order.status == OrderStatus.PAID:
        return
    product = await session.get(Product, order.product_id)
    payment = await _payment_for_order(session, order.id)
    order.status = OrderStatus.PAID
    if payment:
        payment.status = PaymentStatus.SUCCEEDED
    await grant(session, order.user_id, product.credits, f"order-paid:{order.id}", "Development-safe purchase grant")


async def _payment_for_order(session: AsyncSession, order_id: str) -> PaymentRecord | None:
    return await session.scalar(select(PaymentRecord).where(PaymentRecord.order_id == order_id))
