import logging
from pyrogram import Client, filters, emoji
from pyrogram.enums import ParseMode
from pyrogram.errors.exceptions.bad_request_400 import QueryIdInvalid
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultCachedDocument,
    InlineQuery
)
from database.ia_filterdb import get_search_results
from database.users_chats_db import db
from utils import is_subscribed, get_size, temp
from info import CACHE_TIME, AUTH_CHANNEL, SUPPORT_LINK, UPDATES_LINK, FILE_CAPTION

# Disable cache for inline search if force subscription is enabled
cache_time = 0 if AUTH_CHANNEL else CACHE_TIME

# Optional image list (not used currently)
PICS = [
    "https://graph.org/file/bdc720faf2ff35cf92563.jpg",
    "https://graph.org/file/bdc720faf2ff35cf92563.jpg",
]

def is_banned(query: InlineQuery):
    return query.from_user and query.from_user.id in temp.BANNED_USERS

def get_reply_markup():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚡️ ᴜᴘᴅᴀᴛᴇs ᴄʜᴀɴɴᴇʟ ⚡️", url=UPDATES_LINK),
            InlineKeyboardButton("💡 Support Group 💡", url=SUPPORT_LINK)
        ]
    ])

@Client.on_inline_query()
async def inline_search(bot, query: InlineQuery):
    if is_banned(query):
        await query.answer(
            results=[],
            cache_time=0,
            switch_pm_text="You're banned user :(",
            switch_pm_parameter="start"
        )
        return

    if AUTH_CHANNEL:
        btn = await is_subscribed(bot, query, AUTH_CHANNEL)
        if btn:  # user not subscribed
            btn.append([InlineKeyboardButton("🔁 Try Again 🔁", callback_data=f"checksub#inline_{query.from_user.id}")])
            reply_markup = InlineKeyboardMarkup(btn)
            try:
                await query.answer(
                    results=[],
                    cache_time=0,
                    switch_pm_text="You need to subscribe to my channel to use me!",
                    switch_pm_parameter="subscribe"
                )
                await bot.send_message(
                    chat_id=query.from_user.id,
                    text=(
                        f"👋 Hello {query.from_user.mention},\n\n"
                        "Please join my 'Updates Channel' and try again. 😇"
                    ),
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logging.error(f"Error sending subscription message: {e}")
            return

    string = query.query
    offset = int(query.offset or 0)

    files, next_offset, total = await get_search_results(string, offset=offset)

    results = []
    for file in files:
        reply_markup = get_reply_markup()
        caption = FILE_CAPTION.format(
            file_name=file.file_name,
            file_size=get_size(file.file_size),
            caption=file.caption
        )
        results.append(
            InlineQueryResultCachedDocument(
                title=file.file_name,
                document_file_id=file.file_id,
                caption=caption,
                description=f"Size: {get_size(file.file_size)}",
                reply_markup=reply_markup
            )
        )

    if results:
        switch_pm_text = f"{emoji.FILE_FOLDER} Results - {total}"
        if string:
            switch_pm_text += f" For: {string}"
        await query.answer(
            results=results,
            is_personal=True,
            cache_time=cache_time,
            switch_pm_text=switch_pm_text,
            switch_pm_parameter="start",
            next_offset=str(next_offset)
        )
    else:
        switch_pm_text = f"{emoji.CROSS_MARK} No Results"
        if string:
            switch_pm_text += f" For: {string}"
        await query.answer(
            results=[],
            is_personal=True,
            cache_time=cache_time,
            switch_pm_text=switch_pm_text,
            switch_pm_parameter="start"
        )

@Client.on_callback_query(filters.regex(r"^checksub#"))
async def check_subscription(bot, query):
    try:
        if AUTH_CHANNEL and not await is_subscribed(bot, query, AUTH_CHANNEL):
            btn = await is_subscribed(bot, query, AUTH_CHANNEL)
            btn.append([InlineKeyboardButton("🔁 Try Again 🔁", callback_data=f"checksub#inline_{query.from_user.id}")])
            reply_markup = InlineKeyboardMarkup(btn)

            current_text = query.message.text or query.message.caption or ""
            new_text = (
                f"👋 Hello {query.from_user.mention},\n\n"
                "Please join my 'Updates Channel' and try again. 😇"
            )

            if current_text != new_text:
                await query.message.edit_text(
                    text=new_text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
            else:
                await query.answer("Still waiting for you to join the channel.", show_alert=True)
        else:
            await query.message.delete()
            await query.answer("✅ Subscription verified! You can now use the bot.", show_alert=True)

    except QueryIdInvalid:
        await query.answer("⛔ The query is no longer valid.", show_alert=True)
    except Exception as e:
        logging.error(f"Error in check_subscription: {e}")
        await query.answer("❗An error occurred. Please try again later.", show_alert=True)
