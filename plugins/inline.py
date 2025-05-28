import logging, time
from pyrogram import Client, emoji, filters
from pyrogram.enums import ParseMode
from pyrogram.errors.exceptions.bad_request_400 import QueryIdInvalid, UserNotParticipant
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultCachedDocument, InlineQuery
from database.ia_filterdb import get_search_results
from database.users_chats_db import db
from utils import is_subscribed, get_size, temp, get_verify_status, update_verify_status
from info import CACHE_TIME, AUTH_CHANNEL, SUPPORT_LINK, UPDATES_LINK, FILE_CAPTION, IS_VERIFY, VERIFY_EXPIRE
import random

cache_time = 0 if AUTH_CHANNEL else CACHE_TIME

# Sample list of image URLs for reply_photo (replace with actual image URLs)
PICS = [
    "https://graph.org/file/bdc720faf2ff35cf92563.jpg",
    "https://graph.org/file/bdc720faf2ff35cf92563.jpg",
    # Add more image URLs as needed
]

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

    if AUTH_CHANNEL:
        btn = await is_subscribed(bot, query, AUTH_CHANNEL)
        if btn:  # User is not subscribed
            btn.append(
                [InlineKeyboardButton("🔁 Try Again 🔁", callback_data=f"checksub#inline_{query.from_user.id}")]
            )
            reply_markup = InlineKeyboardMarkup(btn)
            try:
                await query.answer(
                    results=[],
                    cache_time=0,
                    switch_pm_text="You need to subscribe to my channel to use me!",
                    switch_pm_parameter="subscribe"
                )
                # Send a message instead of a photo if PICS is empty or to avoid issues
                await bot.send_message(
                    chat_id=query.from_user.id,
                    text=f"👋 Hello {query.from_user.mention},\n\nPlease join my 'Updates Channel' and try again. 😇",
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logging.error(f"Error sending subscription message: {e}")
            return

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

@Client.on_callback_query(filters.regex(r"^checksub#"))
async def check_subscription(bot, query):
    """Handle 'Try Again' callback for subscription check"""
    try:
        if AUTH_CHANNEL and not await is_subscribed(bot, query, AUTH_CHANNEL):
            btn = await is_subscribed(bot, query, AUTH_CHANNEL)
            btn.append(
                [InlineKeyboardButton("🔁 Try Again 🔁", callback_data=f"checksub#inline_{query.from_user.id}")]
            )
            reply_markup = InlineKeyboardMarkup(btn)
            await query.message.edit(
                text=f"👋 Hello {query.from_user.mention},\n\nPlease join my 'Updates Channel' and try again. 😇",
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
        else:
            await query.message.delete()  # Delete the subscription message if user is subscribed
            await query.answer("Subscription verified! You can now use the bot.", show_alert=True)
    except QueryIdInvalid:
        await query.answer("The query is no longer valid.", show_alert=True)
    except Exception as e:
        logging.error(f"Error in check_subscription: {e}")
        await query.answer("An error occurred. Please try again later.", show_alert=True)
