# modules/admin.py

import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from pyrogram.errors import UserIsBlocked, FloodWait

from config import config
from utils.database import (
    get_all_users,
    get_all_projects_count,
    get_all_premium_projects_count,
    get_active_projects_count,
    get_premium_users_count,  # New import
    find_user_by_id,
    get_user_projects,
    increase_user_project_quota,
    get_global_settings,
    update_global_setting,
    get_last_premium_project, # New import
    update_project_config,   # New import
    get_first_locked_project
)
from utils.keyboard_helper import (
    admin_main_keyboard,
    admin_stats_keyboard,
    admin_settings_keyboard,  # New import
    admin_user_management_keyboard,
    admin_user_detail_keyboard,
    admin_back_to_main_keyboard
)
# We need stop_project from the helper now
from utils.deployment_helper import stop_project

ADMIN_IDS = config.Bot.ADMIN_IDS

# Dummy handler for no-op callbacks
@Client.on_callback_query(filters.regex(r"^noop$"))
async def noop_callback(client: Client, query: CallbackQuery):
    await query.answer()

@Client.on_message(filters.command("admin") & filters.user(ADMIN_IDS))
async def admin_panel(client: Client, message: Message):
    await message.reply_text(
        "👑 **Admin Panel**\n\nWelcome. Please choose an option below.",
        reply_markup=admin_main_keyboard()
    )

@Client.on_callback_query(filters.regex(r"^admin_"))
async def admin_callback_router(client: Client, query: CallbackQuery):
    if query.from_user.id not in ADMIN_IDS:
        return await query.answer("Access Denied.", show_alert=True)
    
    data = query.data.split('_')
    action = data[1]

    # --- MAIN MENU & STATS ---
    if action == "main":
        await query.message.edit_text("👑 **Admin Panel**\n\nWelcome.", reply_markup=admin_main_keyboard())
    elif action == "stats":
        total_users = await get_all_users(count_only=True)
        premium_users = await get_premium_users_count()
        total_projects = await get_all_projects_count()
        premium_projects = await get_all_premium_projects_count()
        active_projects = await get_active_projects_count()
        text = (
            "📊 **Bot Statistics**\n\n"
            f"👤 **Total Users:** `{total_users}`\n"
            f"⭐ **Premium Users:** `{premium_users}`\n"
            f"📁 **Total Projects:** `{total_projects}`\n"
            f"💎 **Premium Projects:** `{premium_projects}`\n"
            f"🟢 **Active (Running) Projects:** `{active_projects}`"
        )
        await query.message.edit_text(text, reply_markup=admin_stats_keyboard())

    # --- USER MANAGEMENT ---
    elif action == "users":
        await query.message.edit_text("👤 **User Management**\n\nEnter a user's Telegram ID to manage them.", reply_markup=admin_user_management_keyboard())
    elif action == "finduser":
        try:
            ask_msg = await client.ask(query.from_user.id, "Please send the User ID.", timeout=60)
            await _show_user_details(client, query, int(ask_msg.text))
        except ValueError:
            await query.message.reply_text("❌ Invalid ID.")
        except asyncio.TimeoutError:
            await query.message.reply_text("⏰ Timed out.")
    elif action == "viewuser":
        await _show_user_details(client, query, int(data[2]))
    
    # --- QUOTA MANAGEMENT (REVISED) ---
    elif action == "changequota":
        mod_type = data[2]
        user_id = int(data[3])
        user = await find_user_by_id(user_id)
        current_quota = user.get('project_quota', config.User.FREE_USER_PROJECT_QUOTA)

        if mod_type == 'add':
            new_quota = await increase_user_project_quota(user_id, 1)
            
            # --- NEW LOGIC: Try to unlock a project ---
            project_to_unlock = await get_first_locked_project(user_id)
            if project_to_unlock:
                from datetime import datetime, timedelta
                project_id_str = str(project_to_unlock['_id'])
                # Give it a new 30-day lease on life
                new_expiry = datetime.utcnow() + timedelta(days=30)
                await update_project_config(project_id_str, {'is_locked': False, 'expiry_date': new_expiry})
                
                await query.answer(f"Quota added! Project '{project_to_unlock['name']}' has been UNLOCKED for 30 days.", show_alert=True)
                await client.send_message(user_id, f"✅ An admin has adjusted your quota. Your project `{project_to_unlock['name']}` has been unlocked!")
            else:
                await query.answer(f"Quota increased to {new_quota}! No locked projects to unlock.", show_alert=True)

        elif mod_type == 'remove':
            if current_quota <= config.User.FREE_USER_PROJECT_QUOTA:
                return await query.answer("Cannot reduce quota below the free tier limit.", show_alert=True)
            
            # Reduce quota in DB
            new_quota = await increase_user_project_quota(user_id, -1)
            
            # Find and lock the most recent premium project
            project_to_lock = await get_last_premium_project(user_id)
            if project_to_lock:
                project_id_str = str(project_to_lock['_id'])
                await stop_project(project_id_str)
                await update_project_config(project_id_str, {'is_locked': True})
                await query.answer(f"Quota reduced! Project '{project_to_lock['name']}' has been locked.", show_alert=True)
                await client.send_message(user_id, f"🔒 An admin has adjusted your quota. Your project `{project_to_lock['name']}` is now locked.")
            else:
                await query.answer(f"Quota reduced to {new_quota}! No active premium project was found to lock.", show_alert=True)
        
        await _show_user_details(client, query, user_id) # Refresh the user view

    # --- GLOBAL SETTINGS & BROADCAST --- (Rest of the function is the same as before)
    elif action == "settings":
        settings = await get_global_settings()
        ram = settings.get('free_user_ram_mb', config.User.FREE_USER_RAM_MB)
        await query.message.edit_text(
            f"⚙️ **Global Settings**\n\nManage global configurations for all users.",
            reply_markup=admin_settings_keyboard(ram)
        )
    elif action == "setfreeram":
        try:
            ask_ram = await client.ask(query.from_user.id, "Enter the new RAM amount in MB for FREE users (e.g., `512`).", timeout=60)
            new_ram = int(ask_ram.text)
            if not (50 <= new_ram <= 1024):
                raise ValueError("RAM must be between 50 and 1024 MB.")
            
            await update_global_setting("free_user_ram_mb", new_ram)
            await query.answer(f"Free user RAM set to {new_ram} MB!", show_alert=True)
        except (ValueError, asyncio.TimeoutError) as e:
            await query.message.reply_text(f"❌ Operation failed. Please provide a valid number. Error: {e}")
        
        query.data = "admin_settings"
        await admin_callback_router(client, query)

    elif action == "broadcast":
        try:
            prompt = await client.ask(query.from_user.id, "➡️ Send message to broadcast or /cancel.", timeout=300)
            if prompt.text == "/cancel":
                return await prompt.reply_text("Broadcast cancelled.", reply_markup=admin_main_keyboard())
            
            confirm = await client.ask(query.from_user.id, "Send `yes` to confirm broadcast.", timeout=60)
            if confirm.text.lower() != 'yes':
                return await confirm.reply_text("Broadcast cancelled.", reply_markup=admin_main_keyboard())
            
            await _run_broadcast(client, query, prompt)
        except asyncio.TimeoutError:
            await query.message.reply_text("⏰ Timed out. Broadcast cancelled.", reply_markup=admin_main_keyboard())

    await query.answer()

async def _show_user_details(client: Client, query: CallbackQuery, user_id: int):
    """Helper function to display a detailed view of a user (Revised)."""
    user = await find_user_by_id(user_id)
    if not user:
        return await query.message.edit_text(f"❌ User `{user_id}` not found.", reply_markup=admin_user_management_keyboard())

    projects = await get_user_projects(user_id)
    project_list_str = "\n".join(
        f"- `{p['name']}` {'🟢' if p.get('execution_info',{}).get('is_running') else '🔴'}{'⭐' if p.get('is_premium') else '🆓'}{'🔒' if p.get('is_locked') else ''}"
        for p in projects
    ) or "No projects found."

    current_quota = user.get('project_quota', config.User.FREE_USER_PROJECT_QUOTA)

    text = (
        f"👤 **User Details: `{user_id}`**\n\n"
        f"**Username:** `@{user.get('username', 'N/A')}`\n"
        f"**Joined:** `{user.get('joined_at', 'N/A').strftime('%Y-%m-%d')}`\n\n"
        f"**Projects:**\n{project_list_str}"
    )
    
    await query.message.edit_text(text, reply_markup=admin_user_detail_keyboard(user_id, current_quota))


async def _run_broadcast(client: Client, query: CallbackQuery, broadcast_msg: Message):
    # (Your broadcast logic can stay the same, I'm just including it for the file to be complete)
    users = await get_all_users()
    total_users = len(users)
    status_msg = await query.message.edit_text(f"📢 Starting broadcast to `{total_users}` users...")

    sent, failed = 0, 0
    start_time = asyncio.get_event_loop().time()

    for user in users:
        try:
            await broadcast_msg.copy(user['_id'])
            sent += 1
            await asyncio.sleep(0.05)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await broadcast_msg.copy(user['_id'])
            sent += 1
        except Exception:
            failed += 1
        
    elapsed = int(asyncio.get_event_loop().time() - start_time)
    await status_msg.edit_text(
        f"✅ **Broadcast Complete**\n\n"
        f"Sent: `{sent}`\nFailed: `{failed}`\n"
        f"Total time: `{elapsed}`s.",
        reply_markup=admin_back_to_main_keyboard()
    )