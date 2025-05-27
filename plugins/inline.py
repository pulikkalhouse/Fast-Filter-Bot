import logging, time
from pyrogram import Client, emoji, filters
from pyrogram.errors.exceptions.bad_request_400 import QueryIdInvalid
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultCachedDocument, InlineQuery
from database.ia_filterdb import get_search_results
from database.users_chats_db import db
from utils import is_subscribed, get_size, temp, get_verify_status, update_verify_status, get_settings
from info import CACHE_TIME, AUTH_CHANNEL, SUPPORT_LINK, UPDATES_LINK, FILE_CAPTION, IS_VERIFY, VERIFY_EXPIRE, IS_FSUB

cache_time = 0 if AUTH_CHANNEL else CACHE_TIME

def is_banned(query: InlineQuery):
    return query.from_user and query.from_user.id in temp.BANNED_USERS

@Client.on_inline_query()
async def inline_search(bot, query):
    """Show search results for given inline query"""

    if is_banned(query):
        await query.answer(results=[],
                           cache_time=0,
                           switch_pm_text="You're banned user :(",
                           switch_pm_parameter="start")
        return

    # Check for force subscription
    if AUTH_CHANNEL and not await is_subscribed(bot, query, AUTH_CHANNEL):
        await query.answer(results=[],
                           cache_time=0,
                           switch_pm_text='ʏᴏᴜ ʜᴀᴠᴇ ᴛᴏ ꜱᴜʙꜱᴄʀɪʙᴇ ᴍʏ ᴄʜᴀɴɴᴇʟ ᴛᴏ ᴜꜱᴇ ᴍᴇ !!',
                           switch_pm_parameter="subscribe")
        return

    # Additional check for dynamic force subscription settings
    try:
        # Get user settings if you have per-user force subscription
        user_id = query.from_user.id
        settings = await get_settings(user_id)
        
        if settings and settings.get('is_fsub', IS_FSUB):
            fsub_channels = settings.get('fsub', [])
            if fsub_channels:
                # Check subscription to required channels
                for channel in fsub_channels:
                    if not await is_subscribed(bot, query, channel):
                        await query.answer(results=[],
                                         cache_time=0,
                                         switch_pm_text='ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟs ᴛᴏ ᴜꜱᴇ ɪɴʟɪɴᴇ ꜱᴇᴀʀᴄʜ',
                                         switch_pm_parameter=f"fsub_{user_id}")
                        return
    except Exception as e:
        logging.error(f"Error checking force subscription in inline: {e}")

    results = []
    string = query.query
    offset = int(query.offset or 0)
    files, next_offset, total = await get_search_results(string, offset=offset)

    for file in files:
        reply_markup = get_reply_markup()
        f_caption = FILE_CAPTION.format(
            file_name=file.file_name,
            file_size=get_size(file.file_size),
            caption=file.caption
        )
        results.append(
            InlineQueryResultCachedDocument(
                title=file.file_name,
                document_file_id=file.file_id,
                caption=f_caption,
                description=f'Size: {get_size(file.file_size)}',
                reply_markup=reply_markup))

    if results:
        switch_pm_text = f"{emoji.FILE_FOLDER} Results - {total}"
        if string:
            switch_pm_text += f' For: {string}'
        await query.answer(results=results,
                        is_personal=True,
                        cache_time=cache_time,
                        switch_pm_text=switch_pm_text,
                        switch_pm_parameter="start",
                        next_offset=str(next_offset))
    else:
        switch_pm_text = f'{emoji.CROSS_MARK} No Results'
        if string:
            switch_pm_text += f' For: {string}'
        await query.answer(results=[],
                           is_personal=True,
                           cache_time=cache_time,
                           switch_pm_text=switch_pm_text,
                           switch_pm_parameter="start")


def get_reply_markup():
    buttons = [[
        InlineKeyboardButton('⚡️ ᴜᴘᴅᴀᴛᴇs ᴄʜᴀɴɴᴇʟ ⚡️', url=UPDATES_LINK),
        InlineKeyboardButton('💡 Support Group 💡', url=SUPPORT_LINK)
    ]]
    return InlineKeyboardMarkup(buttons)


# Add this handler to handle the force subscription check when user clicks the inline button
@Client.on_message(filters.command("start") & filters.private)
async def start_handler(bot, message):
    """Handle start command and force subscription checks"""
    
    # Check if it's a force subscription callback
    if len(message.command) > 1:
        parameter = message.command[1]
        
        if parameter == "subscribe":
            # Handle AUTH_CHANNEL subscription
            if AUTH_CHANNEL:
                btn = await is_subscribed(bot, message, AUTH_CHANNEL)
                if btn:
                    btn.append(
                        [InlineKeyboardButton("🔁 Try Again 🔁", callback_data="checksub#start")]
                    )
                    reply_markup = InlineKeyboardMarkup(btn)
                    await message.reply_photo(
                        photo=random.choice(PICS) if 'PICS' in globals() else None,
                        caption=f"👋 Hello {message.from_user.mention},\n\nPlease join my 'Updates Channel' to use inline search. 😇",
                        reply_markup=reply_markup,
                        parse_mode=enums.ParseMode.HTML
                    )
                    return
        
        elif parameter.startswith("fsub_"):
            # Handle dynamic force subscription
            user_id = int(parameter.split("_")[1])
            settings = await get_settings(user_id)
            
            if settings and settings.get('is_fsub', IS_FSUB):
                btn = await is_subscribed(bot, message, settings['fsub'])
                if btn:
                    btn.append(
                        [InlineKeyboardButton("🔁 Try Again 🔁", callback_data=f"checksub#{parameter}")]
                    )
                    reply_markup = InlineKeyboardMarkup(btn)
                    await message.reply_photo(
                        photo=random.choice(PICS) if 'PICS' in globals() else None,
                        caption=f"👋 Hello {message.from_user.mention},\n\nPlease join the required channels to use inline search. 😇",
                        reply_markup=reply_markup,
                        parse_mode=enums.ParseMode.HTML
                    )
                    return
    
    # Regular start message if no force subscription needed
    await message.reply_text("Welcome! You can now use inline search by typing @yourbotusername in any chat.")


# Add callback handler for subscription check
@Client.on_callback_query(filters.regex(r"^checksub#"))
async def check_subscription_callback(bot, callback_query):
    """Handle subscription check callback"""
    
    parameter = callback_query.data.split("#")[1]
    
    if parameter == "start":
        # Check AUTH_CHANNEL subscription
        if AUTH_CHANNEL and not await is_subscribed(bot, callback_query.message, AUTH_CHANNEL):
            await callback_query.answer("❌ You haven't subscribed to the channel yet!", show_alert=True)
            return
    
    elif parameter.startswith("fsub_"):
        # Check dynamic force subscription
        user_id = int(parameter.split("_")[1])
        settings = await get_settings(user_id)
        
        if settings and settings.get('is_fsub', IS_FSUB):
            fsub_channels = settings.get('fsub', [])
            for channel in fsub_channels:
                if not await is_subscribed(bot, callback_query.message, channel):
                    await callback_query.answer("❌ You haven't subscribed to all required channels yet!", show_alert=True)
                    return
    
    # If all checks pass
    await callback_query.message.delete()
    await callback_query.answer("✅ Great! You can now use inline search.", show_alert=True)
