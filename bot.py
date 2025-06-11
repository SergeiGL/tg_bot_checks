# docker build . -t tg_bot_collect_checks-bot

import math
import traceback
import sys
from telegram import (
    Update,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackContext,
    CommandHandler,
    MessageHandler,
    AIORateLimiter,
    filters
)

import database
from send_telegram_message import send_telegram_message
import config
import google_sheets
import asyncio

if sys.platform.startswith("win"):
    # switch from Proactor to Selector loop
    from asyncio import WindowsSelectorEventLoopPolicy
    asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())



# /start special entry function
# THE WHOLE CODE IS BUILD WITH THE ASSUMPTION THAT THE USER WILL START FROM HERE
async def start_handle(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    username = update.effective_user.username or "NO_USERNAME"
    
    # Ignore group
    if chat_id < 0:
        return
    
    sum_to_pay, count, total_people, total_sum, paid = await context.application.bot_data["db"].get_user_data(chat_id=chat_id, username=username)
    
    # The user does not exist in the Google Sheets
    if paid is None:
        await context.bot.send_message(chat_id=chat_id, text=config.username_not_found_text.format(username), parse_mode = "HTML")
        return
     
    # The user has already paid
    if paid==True:
        await context.bot.send_message(chat_id=chat_id, text=config.already_done_text, parse_mode = "HTML")
        return
    
    await context.bot.send_message(chat_id=chat_id, text=config.start_text.format(count+1, total_people, sum_to_pay, sum_to_pay, math.ceil(total_sum/total_people), math.ceil(sum_to_pay*config.GEOM_SEQ_R), round((config.GEOM_SEQ_R-1)*100, 2)), parse_mode = "HTML")


async def post_init(application: Application) -> None:
    # Hide the default commands menu
    await application.bot.set_my_commands([])

    # Create the AsyncDatabase instance:
    db = await database.AsyncDatabase.create()
    application.bot_data["db"] = db


async def message_handle(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    # Сheck if message is edited (to avoid AttributeError: 'NoneType' object has no attribute 'from_user')
    # or if the message is from a group (chat_id < 0)
    if update.edited_message or (not update.message) or chat_id < 0:
        return
    
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        file = await context.bot.get_file(file_id)
        file_url = file.file_path
        
        username = update.effective_user.username or "NO_USERNAME"
        sum_to_pay, count, total_people, total_sum, paid = await context.application.bot_data["db"].get_user_data(chat_id=chat_id, username=username)

        if not paid is None:
            if paid == False:
                unique_invite_link = await context.bot.create_chat_invite_link(chat_id=config.group_chat_id, 
                                                                                member_limit=1)
                unique_invite_link = unique_invite_link.invite_link
                
                count, sum_to_pay, elapsed_interval = await context.application.bot_data["db"].insert_check_link(
                    chat_id=chat_id,
                    username=username,
                    check_link=file_url,
                    check_file_id=file_id,
                )
                                
                row_number = await google_sheets.color_and_insert_data(username, count, sum_to_pay, elapsed_interval)
                                
                for alert_chat_id in config.telegram_alerts_chats:
                    await context.bot.send_photo(
                        chat_id=alert_chat_id,
                        photo=file_id,
                        caption=config.alert_text.format(count+1, username, sum_to_pay),
                        parse_mode="HTML"
                    )
                
                await context.bot.send_message(chat_id=chat_id, text=config.success_text.format(unique_invite_link, row_number), parse_mode = "HTML")
            else: # already paid (green in the table)
                await context.bot.send_message(chat_id=chat_id, text=config.already_done_text, parse_mode = "HTML")
        else: # no such row in the table
            await context.bot.send_message(chat_id=chat_id, text=config.username_not_found_text.format(username), parse_mode = "HTML")
    else: # no photo in the message
        await context.bot.send_message(chat_id=chat_id, text=config.wrong_message_text, parse_mode = "HTML")
    

async def error_handle(update: Update, context: CallbackContext) -> None:
    exc_info = sys.exc_info()

    if exc_info[0] is None:
        error_message = "ERROR\nbot.py:\nAn error occurred, but no exception was raised."
    else:
        tb_list = traceback.format_exception(*exc_info)
        tb_string = ''.join(tb_list)
        
        error_message = f"ERROR\nbot.py:\n{tb_string}"
    
    try:
        await send_telegram_message(error_message)
        print(error_message)
    except: pass
    
    await start_handle(update, context)



if __name__ == "__main__":
    print("Starting...")
    
    application = (
        ApplicationBuilder()
        .token(config.telegram_bot_token)
        .concurrent_updates(True)
        .rate_limiter(AIORateLimiter(max_retries=5))
        .http_version("1.1")
        .get_updates_http_version("1.1")
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start_handle))
    application.add_handler(MessageHandler(filters.ALL, message_handle))
    application.add_error_handler(error_handle)


    application.run_polling()