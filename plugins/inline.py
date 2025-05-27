import logging, time, random
from pyrogram import Client, emoji, filters, enums
from pyrogram.errors.exceptions.bad_request_400 import QueryIdInvalid
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultCachedDocument, InlineQuery
from database.ia_filterdb import get_search_results
from database.users_chats_db import db
from utils import is_subscribed, get_size, temp, get_verify_status, update_verify_status, get_settings
from info import CACHE_TIME, AUTH_CHANNEL, SUPPORT_LINK, UPDATES_LINK, FILE_CAPTION, IS_VERIFY, VERIFY_EXPIRE, IS_FSUB

cache_time = 0 if AUTH_CHANNEL else CACHE_TIME

def is_banned(query: InlineQuery):
    return query.from_user and query.from_user.id in temp.BANNED_USERS

def normalize_channels(channels):
    """Normalize channel input to a list of valid channel IDs"""
    if not channels:
        return []
    
    # Convert to list if it's a single value
    if isinstance(channels, (int, str)):
        channels = [channels]
    elif not isinstance(channels, list):
        # Handle any other type by converting to list
        channels = [channels] if channels else []
    
    # Flatten nested lists if they exist
    if isinstance(channels, list):
        flattened = []
        for channel in channels:
            if isinstance(channel, list):
                flattened.extend(channel)
            elif channel is not None and str(channel).strip():  # Skip None/empty values
                # Convert to int if it's a numeric string (channel ID)
                try:
                    if isinstance(channel, str) and channel.lstrip('-').isdigit():
                        flattened.append(int(channel))
                    elif isinstance(channel, int):
                        flattened.append(channel)
                    elif isinstance(channel, str) and channel.strip():
                        flattened.append(channel)  # Keep as string if it's a username
                except ValueError:
                    continue
        channels = flattened
    
    return channels

async def check_all_subscriptions(bot, query_or_message, channels):
    """Check subscription to all channels and return unsubscribed ones"""
    if not channels:
        return []
    
    unsubscribed_channels = []
    for channel in channels:
        try:
            # Skip invalid channel values
            if channel is None or str(channel).strip() == '':
                continue
                
            if not await is_subscribed(bot, query_or_message, channel):
                unsubscribed_channels.append(channel)
        except Exception as channel_error:
            logging.error(f"Error checking subscription for channel {channel}: {channel_error}")
            unsubscribed_channels.append(channel)
    
    return unsubscribed_channels

@Client.on_inline_query()
async def inline_search(bot, query):
    """Show search results for given inline query"""

    if is_banned(query):
        await query.answer(results=[],
                           cache_time=0,
                           switch_pm_text="You're banned user :(",
                           switch_pm_parameter="start")
        return

    # Normalize AUTH_CHANNEL to list
    auth_channels = normalize_channels(AUTH_CHANNEL)
    
    # Check for basic AUTH_CHANNEL subscription
    if auth_channels:
        unsubscribed_auth = await check_all_subscriptions(bot, query, auth_channels)
        if unsubscribed_auth:
            channel_count = len(auth_channels)
            switch_text = f'ᴊᴏɪɴ {channel_count} ᴄʜᴀɴɴᴇʟ{"s" if channel_count > 1 else ""} ᴛᴏ ᴜꜱᴇ ᴍᴇ !!'
            await query.answer(results=[],
                             cache_time=0,
                             switch_pm_text=switch_text,
                             switch_pm_parameter="subscribe")
            return

    # Additional check for dynamic force subscription settings
    try:
        user_id = query.from_user.id
        settings = await get_settings(user_id)
        
        if settings and settings.get('is_fsub', IS_FSUB):
            fsub_channels = normalize_channels(settings.get('fsub'))
            
            if fsub_channels:
                unsubscribed_fsub = await check_all_subscriptions(bot, query, fsub_channels)
                
                if unsubscribed_fsub:
                    channel_count = len(fsub_channels)
                    switch_text = f'ᴊᴏɪɴ {channel_count} ᴄʜᴀɴɴᴇʟ{"s" if channel_count > 1 else ""} ᴛᴏ ᴜꜱᴇ ɪɴʟɪɴᴇ'
                    await query.answer(results=[],
                                     cache_time=0,
                                     switch_pm_text=switch_text,
                                     switch_pm_parameter=f"fsub_{user_id}")
                    return
    except Exception as e:
        logging.error(f"Error checking force subscription in inline: {e}")
        # Log more details about the error
        import traceback
        logging.error(f"Full traceback: {traceback.format_exc()}")

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


async def get_subscription_buttons(bot, message, channels):
    """Get subscription buttons for all unsubscribed channels"""
    all_buttons = []
    unsubscribed_count = 0
    
    for channel in channels:
        try:
            # Skip invalid channel values
            if channel is None or str(channel).strip() == '':
                continue
                
            btn = await is_subscribed(bot, message, channel)
            if btn:
                all_buttons.extend(btn)
                unsubscribed_count += 1
        except Exception as e:
            logging.error(f"Error getting subscription button for channel {channel}: {e}")
    
    return all_buttons, unsubscribed_count


@Client.on_message(filters.command("start") & filters.private)
async def start_handler(bot, message):
    """Handle start command and force subscription checks"""
    
    # Check if it's a force subscription callback
    if len(message.command) > 1:
        parameter = message.command[1]
        
        if parameter == "subscribe":
            # Handle AUTH_CHANNEL subscription
            auth_channels = normalize_channels(AUTH_CHANNEL)
            if auth_channels:
                all_buttons, unsubscribed_count = await get_subscription_buttons(bot, message, auth_channels)
                
                if all_buttons:
                    all_buttons.append(
                        [InlineKeyboardButton("🔁 Try Again 🔁", callback_data="checksub#start")]
                    )
                    reply_markup = InlineKeyboardMarkup(all_buttons)
                    
                    channel_text = f"{unsubscribed_count} channel{'s' if unsubscribed_count > 1 else ''}"
                    await message.reply_photo(
                        photo=random.choice(PICS) if 'PICS' in globals() else None,
                        caption=f"👋 Hello {message.from_user.mention},\n\nPlease join {channel_text} to use inline search. 😇",
                        reply_markup=reply_markup,
                        parse_mode=enums.ParseMode.HTML
                    )
                    return
        
        elif parameter.startswith("fsub_"):
            # Handle dynamic force subscription for multiple channels
            user_id = int(parameter.split("_")[1])
            settings = await get_settings(user_id)
            
            if settings and settings.get('is_fsub', IS_FSUB):
                fsub_channels = normalize_channels(settings.get('fsub'))
                
                if fsub_channels:
                    all_buttons, unsubscribed_count = await get_subscription_buttons(bot, message, fsub_channels)
                    
                    if all_buttons:
                        # Add try again button
                        all_buttons.append(
                            [InlineKeyboardButton("🔁 Try Again 🔁", callback_data=f"checksub#{parameter}")]
                        )
                        reply_markup = InlineKeyboardMarkup(all_buttons)
                        
                        channel_text = f"{unsubscribed_count} channel{'s' if unsubscribed_count > 1 else ''}"
                        await message.reply_photo(
                            photo=random.choice(PICS) if 'PICS' in globals() else None,
                            caption=f"👋 Hello {message.from_user.mention},\n\nPlease join {channel_text} to use inline search. 😇",
                            reply_markup=reply_markup,
                            parse_mode=enums.ParseMode.HTML
                        )
                        return
    
    # Regular start message if no force subscription needed
    await message.reply_text("Welcome! You can now use inline search by typing @yourbotusername in any chat.")


@Client.on_callback_query(filters.regex(r"^checksub#"))
async def check_subscription_callback(bot, callback_query):
    """Handle subscription check callback"""
    
    parameter = callback_query.data.split("#")[1]
    
    if parameter == "start":
        # Check AUTH_CHANNEL subscription
        auth_channels = normalize_channels(AUTH_CHANNEL)
        if auth_channels:
            unsubscribed_auth = await check_all_subscriptions(bot, callback_query.message, auth_channels)
            if unsubscribed_auth:
                remaining_count = len(unsubscribed_auth)
                total_count = len(auth_channels)
                await callback_query.answer(
                    f"❌ Please join all {total_count} required channels! ({remaining_count} remaining)", 
                    show_alert=True
                )
                return
    
    elif parameter.startswith("fsub_"):
        # Check dynamic force subscription for multiple channels
        user_id = int(parameter.split("_")[1])
        settings = await get_settings(user_id)
        
        if settings and settings.get('is_fsub', IS_FSUB):
            fsub_channels = normalize_channels(settings.get('fsub'))
            
            if fsub_channels:
                unsubscribed_fsub = await check_all_subscriptions(bot, callback_query.message, fsub_channels)
                
                if unsubscribed_fsub:
                    remaining_count = len(unsubscribed_fsub)
                    total_count = len(fsub_channels)
                    await callback_query.answer(
                        f"❌ Please join all {total_count} required channels! ({remaining_count} remaining)", 
                        show_alert=True
                    )
                    return
    
    # If all checks pass
    await callback_query.message.delete()
    await callback_query.answer("✅ Great! You can now use inline search.", show_alert=True)
