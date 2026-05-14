# modules/deployment.py

import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery
from pyrogram.errors import MessageNotModified
from utils.database import get_project_by_id, update_project_config
from utils.deployment_helper import (
    start_project, stop_project, restart_project, get_project_status,
    get_project_logs, get_project_usage, install_project_dependencies
)
from utils.keyboard_helper import project_deployment_keyboard, project_management_keyboard

# --- Main Deployment Menu ---

@Client.on_callback_query(filters.regex(r"^deployment_"))
async def deployment_menu_callback(client: Client, query: CallbackQuery):
    project_id = query.data.split("_")[1]
    project = await get_project_by_id(project_id)

    if not project or project['user_id'] != query.from_user.id:
        return await query.answer("Project not found or access denied.", show_alert=True)
    
    # --- LOCK CHECK ---
    if project.get('is_locked', False):
        return await query.answer("Project is locked. Renew to access deployment menu.", show_alert=True)

    status_text = await get_project_status(project_id, project)
    keyboard = project_deployment_keyboard(project)
    
    text = f"⚙️ **Deployment Menu for `{project['name']}`**\n\n{status_text}"
    try:
        await query.message.edit_text(text, reply_markup=keyboard)
    except MessageNotModified:
        pass # Ignore if message is the same.
    await query.answer()

# --- Dependency Installation ---

@Client.on_callback_query(filters.regex(r"^install_proj_"))
async def install_deps_callback(client: Client, query: CallbackQuery):
    project_id = query.data.split("_")[-1]
    project = await get_project_by_id(project_id)
    if not project or project['user_id'] != query.from_user.id:
        return await query.answer("Access Denied.", show_alert=True)
        
    # --- LOCK CHECK ---
    if project.get('is_locked', False):
        return await query.answer("Project is locked. Renew to install dependencies.", show_alert=True)

    await query.answer("Installing dependencies...", show_alert=False)
    try:
        await query.message.edit_text("🔄 Setting up virtual environment and installing packages from `requirements.txt`...\nThis may take a moment.")
    except MessageNotModified:
        pass

    success, message = await install_project_dependencies(project_id, project)
    
    if success:
        await query.message.edit_text(f"✅ Installation Complete!\n\n{message}")
    else:
        log_file_path = os.path.join(project['path'], "installation_error.log")
        try:
            with open(log_file_path, "w") as f:
                f.write(message)

            await client.send_document(
                chat_id=query.from_user.id,
                document=log_file_path,
                caption="❌ **Installation Failed!**\n\nSee the attached log file for details."
            )
            await query.message.delete()
        except Exception as e:
            # Handle cases where sending the file might fail
            await query.message.edit_text(f"❌ **Installation Failed!**\n\n```\n{message[:3000]}\n```")

        keyboard = project_deployment_keyboard(project)
        await client.send_message(query.from_user.id, "Please fix your `requirements.txt` and try again.", reply_markup=keyboard)

# --- Action Callbacks with Lock Checks ---

@Client.on_callback_query(filters.regex(r"^start_proj_"))
async def start_project_callback(client: Client, query: CallbackQuery):
    project_id = query.data.split("_")[-1] 
    project = await get_project_by_id(project_id)

    if not project or project['user_id'] != query.from_user.id:
        return await query.answer("Access Denied.", show_alert=True)
    
    # --- LOCK CHECK ---
    if project.get('is_locked', False):
        return await query.answer("Project is locked. Renew to start.", show_alert=True)
        
    await query.answer("Starting project...")
    try:
        success, message = await start_project(project_id, project)
        await query.message.reply_text(
            f"✅ Project `{project['name']}` started.\n`{message}`" if success 
            else f"❌ Failed to start project `{project['name']}`.\n**Reason:** {message}"
        )
    except Exception as e:
        await query.message.reply_text(f"An error occurred: {e}")

@Client.on_callback_query(filters.regex(r"^stop_proj_"))
async def stop_project_callback(client: Client, query: CallbackQuery):
    project_id = query.data.split("_")[-1]
    project = await get_project_by_id(project_id)

    if not project or project['user_id'] != query.from_user.id:
        return await query.answer("Access Denied.", show_alert=True)
    
    # We allow stopping a locked project. This is a failsafe. No lock check here.

    await query.answer("Stopping project...")
    success, message = await stop_project(project_id)
    await query.message.reply_text(
        f"⏹️ Project `{project['name']}` stopped.\n`{message}`" if success 
        else f"❌ Failed to stop project `{project['name']}`.\n**Reason:** {message}"
    )

@Client.on_callback_query(filters.regex(r"^restart_proj_"))
async def restart_project_callback(client: Client, query: CallbackQuery):
    project_id = query.data.split("_")[-1]
    project = await get_project_by_id(project_id)

    if not project or project['user_id'] != query.from_user.id:
        return await query.answer("Access Denied.", show_alert=True)
        
    # --- LOCK CHECK ---
    if project.get('is_locked', False):
        return await query.answer("Project is locked. Renew to restart.", show_alert=True)

    await query.answer("Restarting project...")
    success, message = await restart_project(project_id, project)
    await query.message.reply_text(
        f"🔁 Project `{project['name']}` restarted." if success 
        else f"❌ Failed to restart project `{project['name']}`.\n**Reason:** {message}"
    )

@Client.on_callback_query(filters.regex(r"^logs_proj_"))
async def logs_project_callback(client: Client, query: CallbackQuery):
    project_id = query.data.split("_")[-1]
    project = await get_project_by_id(project_id)

    if not project or project['user_id'] != query.from_user.id:
        return await query.answer("Access Denied.", show_alert=True)
        
    # --- LOCK CHECK ---
    if project.get('is_locked', False):
        return await query.answer("Project is locked. Renew to view logs.", show_alert=True)

    await query.answer("Fetching logs...")
    log_file_path = await get_project_logs(project_id)
    if os.path.exists(log_file_path) and os.path.getsize(log_file_path) > 0:
        await client.send_document(
            chat_id=query.from_user.id,
            document=log_file_path,
            caption=f"📋 Logs for `{project['name']}`."
        )
    else:
        await query.message.reply_text("No logs found for this project yet.")

@Client.on_callback_query(filters.regex(r"^status_proj_|usage_proj_"))
async def status_or_usage_callback(client: Client, query: CallbackQuery):
    project_id = query.data.split("_")[-1]
    project = await get_project_by_id(project_id)

    if not project or project['user_id'] != query.from_user.id:
        return await query.answer("Access Denied.", show_alert=True)
        
    # --- LOCK CHECK ---
    # We allow checking status/usage even if locked, to see if it crashed etc.
    # if project.get('is_locked', False):
    #     return await query.answer("Project is locked. Renew to check status.", show_alert=True)

    action = query.data.split("_")[0]
    if action == "status":
        await query.answer("Fetching status...")
        status_text = await get_project_status(project_id, project, detailed=True)
        keyboard = project_deployment_keyboard(project) # Re-add keyboard for further actions
        await query.message.edit_text(status_text, reply_markup=keyboard)
    elif action == "usage":
        await query.answer("Checking resource usage...")
        usage_info = await get_project_usage(project_id)
        await query.message.edit_text(usage_info)

@Client.on_callback_query(filters.regex(r"^editcmd_proj_"))
async def edit_cmd_callback(client: Client, query: CallbackQuery):
    project_id = query.data.split("_")[-1]
    project = await get_project_by_id(project_id)
    if not project or project['user_id'] != query.from_user.id:
        return await query.answer("Access Denied.", show_alert=True)
        
    # --- LOCK CHECK ---
    if project.get('is_locked', False):
        return await query.answer("Project is locked. Renew to edit the run command.", show_alert=True)

    try:
        command_msg = await client.ask(
            chat_id=query.from_user.id,
            text=(
                f"Enter the new run command for `{project['name']}`.\n"
                f"Current: `{project.get('run_command', 'python3 main.py')}`\n\n"
                "Example: `python3 bot.py`"
            ),
            timeout=120
        )
        new_command = command_msg.text.strip()
        if new_command:
            await update_project_config(project_id, {"run_command": new_command})
            await command_msg.reply_text(f"✅ Run command updated to: `{new_command}`")
        else:
            await command_msg.reply_text("❌ Invalid command. Nothing changed.")
    except asyncio.TimeoutError:
        await query.message.reply_text("Cancelled due to timeout.")
    
    # Refresh the deployment menu
    query.data = f"deployment_{project_id}" 
    await deployment_menu_callback(client, query)


@Client.on_callback_query(filters.regex(r"^back_to_main_"))
async def back_to_main_menu(client: Client, query: CallbackQuery):
    project_id = query.data.split("_")[-1]
    project = await get_project_by_id(project_id)
    if not project or project['user_id'] != query.from_user.id:
        return await query.answer("Access Denied.", show_alert=True)
        
    keyboard = project_management_keyboard(project)
    await query.message.edit_text(f"👇 Manage your project `{project['name']}` below.", reply_markup=keyboard)
    await query.answer()