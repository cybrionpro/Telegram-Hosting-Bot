# modules/premium.py

from pyrogram import Client, filters, types
from pyrogram.types import CallbackQuery, Message, PreCheckoutQuery
from datetime import datetime, timedelta

from config import config
from utils.database import (
    increase_user_project_quota,
    get_project_by_id,
    update_project_config
)

# -------------------------------------------------------------------------------- #
# 1. HANDLERS FOR PURCHASING A NEW PROJECT SLOT
# -------------------------------------------------------------------------------- #

@Client.on_callback_query(filters.regex(r"^buy_project_slot$"))
async def send_slot_invoice(client: Client, callback_query: CallbackQuery):
    """
    Initiates the payment process for buying one new project slot.
    This is triggered when a user hits their project limit and wants more.
    """
    # The system uses one plan for all purchases.
    plan_key = '1'
    plan_details = config.Premium.PLANS.get(plan_key)

    if not plan_details:
        await callback_query.answer("Error: Premium plan not configured. Contact admin.", show_alert=True)
        return

    # Payload format: purpose_plankey_userid
    invoice_payload = f"purchase-slot_{plan_key}_{callback_query.from_user.id}"

    try:
        await callback_query.message.edit_text(
            "✨ **Proceeding to Checkout**\n\n"
            "You are about to purchase one additional project slot. You will be redirected to the payment screen."
        )
    except Exception:
        # Message might have been deleted, proceed anyway.
        pass

    # Send the invoice to the user.
    # --- Corrected Version ---
    await client.send_invoice(
        chat_id=callback_query.from_user.id,
        title=plan_details['name'],
        description=plan_details['description'],
        payload=invoice_payload, # <-- FIX: Pass the string directly
        currency=config.Premium.CURRENCY,
        prices=[
            types.LabeledPrice(
                label=f"1 Project Slot (Renews Monthly*)",
                amount=plan_details['stars']
            )
        ]
    )
    await callback_query.answer()

# -------------------------------------------------------------------------------- #
# 2. HANDLERS FOR RENEWING AN EXPIRED PROJECT
# -------------------------------------------------------------------------------- #

@Client.on_callback_query(filters.regex(r"^renew_project_(\w+)$"))
async def send_renewal_invoice(client: Client, callback_query: CallbackQuery):
    """
    Initiates the payment process to renew a specific, expired/locked project.
    """
    project_id = callback_query.matches[0].group(1)
    project = await get_project_by_id(project_id)

    # Security and validity checks
    if not project or project['user_id'] != callback_query.from_user.id:
        await callback_query.answer("Project not found or access denied.", show_alert=True)
        return
    
    if not project.get('is_locked', False):
        await callback_query.answer("This project is active and does not need renewal.", show_alert=True)
        return

    plan_key = '1' # Use the same plan for cost and duration
    plan_details = config.Premium.PLANS.get(plan_key)
    
    if not plan_details:
        await callback_query.answer("Error: Premium plan not configured. Contact admin.", show_alert=True)
        return

    # Payload format: purpose_plankey_userid_projectid
    invoice_payload = f"renew-project_{plan_key}_{callback_query.from_user.id}_{project_id}"

    
    try:
        await callback_query.message.edit_text(
            f"✨ **Renewing Project `{project['name']}`**\n\n"
            "Proceeding to checkout to unlock your project for another 30 days."
        )
    except Exception:
        pass

    # --- Corrected Version ---
    await client.send_invoice(
        chat_id=callback_query.from_user.id,
        title=f"Renew Project: {project['name']}",
        description=f"Unlocks `{project['name']}` and extends its runtime for {plan_details['duration_days']} days.",
        payload=invoice_payload, # <-- FIX: Pass the string directly
        currency=config.Premium.CURRENCY,
        prices=[
            types.LabeledPrice(
                label=f"Renewal ({plan_details['duration_days']} Days)",
                amount=plan_details['stars']
            )
        ]
    )
    await callback_query.answer()

# -------------------------------------------------------------------------------- #
# 3. SHARED PAYMENT PROCESSING LOGIC
# -------------------------------------------------------------------------------- #

@Client.on_pre_checkout_query()
async def pre_checkout_handler(client: Client, query: PreCheckoutQuery):
    """
    Confirms to Telegram that the bot is ready to process the payment.
    This is a mandatory step from Telegram.
    """
    await query.answer(True)


# --- Corrected Version ---
# In modules/premium.py
# REPLACE the entire function

@Client.on_message(filters.successful_payment)
async def successful_payment_handler(client: Client, message: Message):
    """
    This handler is triggered after ANY Stars payment is completed.
    It inspects the invoice payload to decide what action to perform.
    """
    invoice_payload = message.successful_payment.payload
    try:
        # payload format is now: purpose_plankey_userid_optional-projectid
        payload_parts = invoice_payload.split('_')
        
        purpose = payload_parts[0]
        plan_key = payload_parts[1]
        user_id = int(payload_parts[2])

        plan_details = config.Premium.PLANS.get(plan_key)
        if not plan_details:
            raise ValueError(f"Invalid plan key '{plan_key}' in payload.")

        # --- CORRECTED LOGIC ---
        # --- BRANCH 1: User bought a new project slot ---
        if purpose == "purchase-slot":
            new_quota = await increase_user_project_quota(user_id, 1)
            await client.send_message(
                chat_id=user_id,
                text=(
                    f"**✅ Payment Successful!**\n\n"
                    f"Thank you! One project slot has been added to your account.\n"
                    f"You now have a total quota of **{new_quota}** project(s).\n\n"
                    "Use `/newproject` to start creating your new premium project!"
                )
            )

        # --- BRANCH 2: User renewed an existing project ---
        elif purpose == "renew-project":
            if len(payload_parts) < 4:
                raise ValueError("Project ID missing from renewal payload.")
            project_id = payload_parts[3]
            
            new_expiry_date = datetime.utcnow() + timedelta(days=plan_details['duration_days'])
            
            updates = {'expiry_date': new_expiry_date, 'is_locked': False}
            await update_project_config(project_id, updates)

            project = await get_project_by_id(project_id) # Get fresh project data
            
            await client.send_message(
                chat_id=user_id,
                text=(
                    f"**✅ Renewal Successful!**\n\n"
                    f"Project `{project['name']}` has been unlocked and is ready to use.\n"
                    f"It will now run until **{new_expiry_date.strftime('%Y-%m-%d %H:%M UTC')}**."
                )
            )

        else:
            raise ValueError(f"Unknown payment purpose: '{purpose}'")
        
        # await client.refund_star_payment(
        #     user_id=message.from_user.id,
        #     telegram_payment_charge_id=message.successful_payment.telegram_payment_charge_id
        # )
            
        # await message.reply_text(
        #     "**⚠️ This is a test.**\n\n"
        #     "Your payment has been **successfully refunded**, and your premium status has been removed. "
        #     "Thank you for helping test the system!"
        # )


    except Exception as e:
        error_msg = (
            "An unexpected error occurred while processing your payment. "
            "Your payment was successful, but the feature could not be activated automatically.\n\n"
            "**Please contact the bot admin for assistance.**"
        )
        # await client.refund_star_payment(
        #     user_id=message.from_user.id,
        #     telegram_payment_charge_id=message.successful_payment.telegram_payment_charge_id
        # )
            
        # await message.reply_text(
        #     "**⚠️ This is a test.**\n\n"
        #     "Your payment has been **successfully refunded**, and your premium status has been removed. "
        #     "Thank you for helping test the system!"
        # )

        print(f"CRITICAL ERROR in successful_payment_handler: {e}\nPayload: {invoice_payload}")
        await client.send_message(message.chat.id, error_msg)