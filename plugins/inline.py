import logging, time, random
from pyrogram import Client, emoji, filters, enums
from pyrogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, 
    InlineQueryResultCachedDocument, InlineQuery, Message
)
from pyrogram.errors.exceptions.bad_request_400 import QueryIdInvalid

from database.ia_filterdb import get_search_results
from database.users_chats_db import db
from utils import is_subscribed, get_size, temp, get_verify_status, update_verify_status
from info import CACHE_TIME, AUTH_CHANNEL, SUPPORT_LINK, UPDATES_LINK, FILE_CAPTION, IS_VERIFY, VERIFY_EXPIRE, PICS

cache_time = 0 if AUTH_CHANNEL else CACHE_TIME


def is_banned(query: InlineQuery):
    return query.from_user and query.from_user.id in temp.BANNED_USERS


@Client.on_inline_query()
async def inline_search(bot, query: InlineQuery):
    """Show search results for given inline query"""

    if is_banned(query):
        await query.answer(results=[],
                           cache_time=0,
                           switch_pm_text="You're banned user :(",
                           switch_pm_parameter="start")
        return

    if AUTH_CHANNEL and await is_subscribed(bot, query, AUTH_CHANNEL):
        await query.answer(results=[],
                           cache_time=0,
                           switch_pm_text='ʏᴏᴜ ʜᴀᴠᴇ ᴛᴏ ꜱᴜʙꜱᴄʀɪʙᴇ ᴍʏ ᴄʜᴀɴɴᴇʟ ᴛᴏ ᴜꜱᴇ ᴍᴇ !!',
                           switch_pm_parameter="subscribe")
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
                reply_markup=reply_markup
            )
        )

    switch_pm_text = f"{emoji.FILE_FOLDER} Results - {total}" if results else f"{emoji.CROSS_MARK} No Results"
    if string:
        switch_pm_text += f' For: {string}'

    await query.answer(
        results=results,
        is_personal=True,
        cache_time=cache_time,
        switch_pm_text=switch_pm_text,
        switch_pm_parameter="start",
        next_offset=str(next_offset) if results else ""
    )


def get_reply_markup(s):
    buttons = [[
        InlineKeyboardButton('🔎 Search Again', switch_inline_query_current_chat=s or '')
    ],[
        InlineKeyboardButton('⚡️ ᴜᴘᴅᴀᴛᴇs ᴄʜᴀɴɴᴇʟ ⚡️', url=UPDATES_LINK),
        InlineKeyboardButton('💡 Support Group 💡', url=SUPPORT_LINK)
    ]]
    return InlineKeyboardMarkup(buttons)


# ✅ Handle /start subscribe here
@Client.on_message(filters.private & filters.command("start"))
async def handle_inline_subscribe(client, message: Message):
    if len(message.command) > 1 and message.command[1] == "subscribe":
        btn = await is_subscribed(client, message, AUTH_CHANNEL)
        if btn:
            btn.append([InlineKeyboardButton("🔁 Try Again 🔁", callback_data="checksub#inline")])
            await message.reply_photo(
                photo=random.choice(PICS),
                caption=f"👋 Hello {message.from_user.mention},\n\nPlease join the required channels and try again to use inline search. 😇",
                reply_markup=InlineKeyboardMarkup(btn),
                parse_mode=enums.ParseMode.HTML
            )
        else:
            await message.reply(
                f"✅ You’re already subscribed!\n\nTry using inline mode by typing:\n<code>@{temp.U_NAME} filename</code>",
                parse_mode=enums.ParseMode.HTML
            )
