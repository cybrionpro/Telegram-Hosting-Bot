# modules/projects.py

import os
import shutil
import zipfile
import string
import random
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from pyrogram.errors import MessageNotModified

from config import config
from utils.database import (
    add_project,
    get_user_projects,
    get_project_by_id,
    delete_project,
    find_user_by_id,
    update_project_config
)
from utils.keyboard_helper import (
    build_projects_keyboard,
    project_management_keyboard,
    project_locked_keyboard,
    buy_project_slot_keyboard,
    user_stats_keyboard # Import the new keyboard
)
from utils.file_manager import start_filebrowser_session, stop_filebrowser_session
from utils.deployment_helper import stop_project

# --- Configuration ---
PROJECTS_BASE_DIR = os.path.join(os.getcwd(), "projects")
MAX_FILE_SIZE = config.User.MAX_PROJECT_FILE_SIZE

os.makedirs(PROJECTS_BASE_DIR, exist_ok=True)

def generate_password(length=14):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for i in range(length))

# --- Command Handlers ---

@Client.on_message(filters.command("newproject") & filters.private)
async def new_project_command(client: Client, message: Message):
    user_id = message.from_user.id
    user = await find_user_by_id(user_id)
    projects = await get_user_projects(user_id)

    # --- QUOTA CHECK ---
    current_project_count = len(projects)
    user_quota = user.get('project_quota', config.User.FREE_USER_PROJECT_QUOTA)

    if current_project_count >= user_quota:
        await message.reply_text(
            "⚠️ **Project Limit Reached**\n\n"
            f"You have reached your limit of **{user_quota}** project(s).\n\n"
            f"To deploy more, please purchase an additional project slot for **{config.Premium.PLANS['1']['stars']} Stars**.",
            reply_markup=buy_project_slot_keyboard()
        )
        return

    # --- DETERMINE PROJECT TYPE (FREE VS PREMIUM) ---
    is_premium = current_project_count >= config.User.FREE_USER_PROJECT_QUOTA
    
    try:
        project_name_message = await client.ask(
            chat_id=message.chat.id,
            text="✍️ Please enter a name for your new project (e.g., `my-awesome-bot`).\n\nSend /cancel to abort."
        )
        if project_name_message.text == "/cancel":
            return await message.reply_text("Project creation cancelled.")

        project_name = project_name_message.text.strip().replace(" ", "-").lower()
        user_project_dir = os.path.join(PROJECTS_BASE_DIR, str(user_id))
        project_path = os.path.join(user_project_dir, project_name)

        if os.path.exists(project_path):
            return await message.reply_text("❌ A project with this name already exists.")

        fb_user = f"{message.from_user.username or user_id}_{project_name}"
        fb_pass = generate_password()
        
        # --- ADD PROJECT TO DB WITH PREMIUM INFO ---
        expiry_date = None
        ram_limit = config.User.FREE_USER_RAM_MB
        if is_premium:
            plan = config.Premium.PLANS['1']
            expiry_date = datetime.utcnow() + timedelta(days=plan['duration_days'])
            ram_limit = plan['ram_mb']

        project_id = await add_project(user_id, project_name, project_path, fb_user, fb_pass, is_premium, expiry_date, ram_limit)
        
        upload_prompt = await client.ask(
            chat_id=message.chat.id,
            text=(
                f"✅ Project `{project_name}` created!\n"
                f"{'⭐ This is a premium project!' if is_premium else 'This is a free project.'}\n\n"
                f"Please upload the project's `.py` file or a `.zip` archive.\n"
                f"**Max file size:** {MAX_FILE_SIZE // 1024 // 1024} MB."
            )
        )

        if not upload_prompt.document:
            await delete_project(project_id) # Clean up db entry
            return await message.reply_text("⚠️ No file uploaded. Project creation aborted.")

        if upload_prompt.document.file_size > MAX_FILE_SIZE:
            await delete_project(project_id) # Clean up db entry
            return await message.reply_text(f"❌ **File Too Large!** The file exceeds the {MAX_FILE_SIZE // 1024 // 1024} MB limit.")
        
        status_msg = await message.reply_text("Downloading and setting up your project...")
        
        os.makedirs(project_path, exist_ok=True)
        file_path = await client.download_media(upload_prompt.document, file_name=os.path.join(project_path, upload_prompt.document.file_name))
        
        if file_path.endswith('.zip'):
            await status_msg.edit("Extracting zip archive...")
            try:
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    temp_extract_path = os.path.join(project_path, "temp_extract")
                    os.makedirs(temp_extract_path, exist_ok=True)
                    zip_ref.extractall(temp_extract_path)

                extracted_files = os.listdir(temp_extract_path)
                if len(extracted_files) == 1 and os.path.isdir(os.path.join(temp_extract_path, extracted_files[0])):
                    subfolder_path = os.path.join(temp_extract_path, extracted_files[0])
                    for item in os.listdir(subfolder_path):
                        shutil.move(os.path.join(subfolder_path, item), project_path)
                else:
                    for item in extracted_files:
                        shutil.move(os.path.join(temp_extract_path, item), project_path)
                
                shutil.rmtree(temp_extract_path)
                os.remove(file_path)
                await status_msg.edit("✅ Project extracted and ready!")
            except zipfile.BadZipFile:
                shutil.rmtree(project_path)
                await delete_project(project_id)
                return await status_msg.edit("❌ The uploaded file is not a valid zip archive. Please start over.")

        await status_msg.edit(f"✅ **Project `{project_name}` setup complete!**")
        
        project = await get_project_by_id(project_id)
        keyboard = project_management_keyboard(project)
        await message.reply_text(f"👇 Manage your project `{project['name']}` below.", reply_markup=keyboard)

    except Exception as e:
        await message.reply_text(f"An error occurred: {e}")

async def check_and_lock_expired_projects(user_id: int):
    """
    On-demand check to find and lock expired premium projects for a user.
    """
    projects = await get_user_projects(user_id)
    now = datetime.utcnow()
    updated_projects = []
    for project in projects:
        if project.get('is_premium') and not project.get('is_locked') and project.get('expiry_date') and project['expiry_date'] < now:
            await stop_project(str(project['_id'])) # Stop the running process if any
            await update_project_config(str(project['_id']), {'is_locked': True})
            project['is_locked'] = True # Update local copy for immediate use
        updated_projects.append(project)
    return updated_projects

@Client.on_message(filters.command("myproject") & filters.private)
async def my_projects_command(client: Client, message: Message):
    user_id = message.from_user.id
    # Run expiry check before showing projects
    projects = await check_and_lock_expired_projects(user_id)
    
    # The new keyboard will have the stats button even if project list is empty
    keyboard = build_projects_keyboard(projects)
    
    text = "You don't have any projects yet. Use /newproject to create one." if not projects else "Please choose a project to manage:"
    
    await message.reply_text(text, reply_markup=keyboard)


# --- Callback Handlers ---

@Client.on_callback_query(filters.regex(r"^project_select_"))
async def select_project_callback(client: Client, query: CallbackQuery):
    project_id = query.data.split("_")[2]
    
    # Run expiry check again on interaction
    await check_and_lock_expired_projects(query.from_user.id)
    project = await get_project_by_id(project_id)
    
    if not project or project['user_id'] != query.from_user.id:
        return await query.answer("Project not found or access denied.", show_alert=True)
    
    # --- LOCKED PROJECT HANDLING ---
    if project.get('is_locked', False):
        expiry_str = project.get('expiry_date').strftime('%Y-%m-%d %H:%M') if project.get('expiry_date') else "N/A"
        text = (
            f"🔒 **Project Locked: `{project['name']}`**\n\n"
            f"This project's premium subscription expired on **{expiry_str} UTC**.\n"
            f"To continue using it, please renew your subscription."
        )
        keyboard = project_locked_keyboard(project_id)
        await query.message.edit_text(text, reply_markup=keyboard)
    else:
        # --- Normal Project Management ---
        keyboard = project_management_keyboard(project)
        await query.message.edit_text(f"👇 Manage your project `{project['name']}` below.", reply_markup=keyboard)
        
    await query.answer()

@Client.on_callback_query(filters.regex(r"^manage_files_"))
async def manage_files_callback(client: Client, query: CallbackQuery):
    project_id = query.data.split("_")[2]
    project = await get_project_by_id(project_id)

    if not project or project['user_id'] != query.from_user.id:
        return await query.answer("Access Denied.", show_alert=True)
    if project.get('is_locked', False):
        return await query.answer("This project is locked. Please renew to manage files.", show_alert=True)

    try:
        url, port = await start_filebrowser_session(project_id, project)
        fb_creds = project.get('filebrowser_creds', {})
        text = (
            "🌐 **File Manager is Ready!**\n\n"
            f"**URL:** `{url}`\n"
            f"**Username:** `{fb_creds.get('user')}`\n"
            f"**Password:** `{fb_creds.get('pass')}`\n\n"
            "⚠️ **Note:** The file manager will automatically stop after 15 minutes of inactivity."
        )
        keyboard = project_management_keyboard(project, filebrowser_url=url)
        await query.message.edit_reply_markup(reply_markup=keyboard)
        await client.send_message(query.from_user.id, text)
        await query.answer(f"File Manager started on port {port}", show_alert=False)
    except Exception as e:
        await query.answer("❌ Error starting file manager.", show_alert=True)
        print(f"Error starting file manager for project {project_id}: {e}")

@Client.on_callback_query(filters.regex(r"^delete_project_"))
async def delete_project_callback(client: Client, query: CallbackQuery):
    project_id = query.data.split("_")[2]
    from pyrogram.types import InlineKeyboardButton
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, Delete it", callback_data=f"confirm_delete_{project_id}")],
        [InlineKeyboardButton("❌ No, Cancel", callback_data=f"cancel_delete_{project_id}")]
    ])
    await query.message.edit_text("⚠️ **Are you sure? This action cannot be undone.**\n\nThis will permanently delete all project files and data.", reply_markup=keyboard)
    await query.answer()

@Client.on_callback_query(filters.regex(r"^confirm_delete_"))
async def confirm_delete_callback(client: Client, query: CallbackQuery):
    project_id = query.data.split("_")[2]
    project = await get_project_by_id(project_id)
    
    if not project or project['user_id'] != query.from_user.id:
        return await query.answer("Access Denied.", show_alert=True)
        
    await stop_filebrowser_session(project_id, project)
    await stop_project(project_id)

    if os.path.exists(project['path']):
        shutil.rmtree(project['path'])
        
    await delete_project(project_id)
    
    # We do NOT adjust the user's quota, as per the requirement.
    # The paid slot is consumed forever.
    await query.message.edit_text(f"✅ Project `{project['name']}` has been permanently deleted.")
    await query.answer("Project deleted.", show_alert=True)

# In modules/projects.py
# REPLACE the cancel_delete_callback function

@Client.on_callback_query(filters.regex(r"^cancel_delete_"))
async def cancel_delete_callback(client: Client, query: CallbackQuery):
    project_id = query.data.split("_")[2]

    # First, simply edit the text of the message to confirm cancellation.
    # No need for a complex, nested call.
    try:
        await query.message.edit_text("Deletion cancelled. Returning to project menu...")
    except MessageNotModified:
        pass
        
    # Manually change the query's data attribute.
    # This tricks the bot into thinking the user just clicked the "select project" button.
    query.data = f"project_select_{project_id}"
    
    # Now, call the correct function to show the project management menu.
    # This will edit the message again, replacing "Deletion cancelled..."
    await select_project_callback(client, query)

    # Answer the original callback query to remove the "loading" state on the button.
    await query.answer()

# In modules/projects.py
# REPLACE the my_projects_list_callback function

@Client.on_callback_query(filters.regex(r"^(my_projects_list|my_projects_list_refresh)$"))
async def my_projects_list_callback(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    projects = await check_and_lock_expired_projects(user_id)
    
    keyboard = build_projects_keyboard(projects)
    text = "You don't have any projects yet. Use /newproject to create one." if not projects else "Please choose a project to manage:"
    
    try:
        await query.message.edit_text(text, reply_markup=keyboard)
    except MessageNotModified:
        pass
        
    await query.answer()

@Client.on_callback_query(filters.regex(r"^user_stats$"))
async def show_user_stats_callback(client: Client, query: CallbackQuery):
    """
    Calculates and displays the user's personal quota and usage statistics.
    """
    user_id = query.from_user.id
    user = await find_user_by_id(user_id)
    projects = await get_user_projects(user_id)

    # --- Calculate Stats ---
    total_slots = user.get('project_quota', config.User.FREE_USER_PROJECT_QUOTA)
    used_slots = len(projects)
    slots_left = total_slots - used_slots
    free_slots = config.User.FREE_USER_PROJECT_QUOTA
    # Ensure premium slots don't show as negative
    premium_slots = max(0, total_slots - free_slots)
    
    # --- Format the message ---
    text = (
        "📊 **Your Quota & Usage Stats**\n\n"
        "This is a summary of your account's project limits.\n\n"
        f"▫️ **Total Project Slots:** `{total_slots}`\n"
        f"  - 🆓 Free Slots: `{free_slots}`\n"
        f"  - ⭐ Premium Slots: `{premium_slots}`\n\n"
        f"▫️ **Current Usage:**\n"
        f"  - ✅ Slots Used: `{used_slots}`\n"
        f"  - 🟩 Slots Available: `{slots_left}`\n\n"
        "You can purchase more premium slots from the /start menu."
    )
    
    # --- Edit the message with the stats and a back button ---
    try:
        await query.message.edit_text(
            text=text,
            reply_markup=user_stats_keyboard()
        )
    except MessageNotModified:
        pass # Ignore if the stats are unchanged

    await query.answer()