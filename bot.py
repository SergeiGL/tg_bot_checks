# docker build . -t tg_bot_collect_checks-bot

import math
import time
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

from telegram.error import TelegramError
import database
from send_telegram_message import send_telegram_message
import config
import google_sheets


# /start special entry function
# THE WHOLE CODE IS BUILD WITH THE ASSUMPTION THAT THE USER WILL START FROM HERE
async def start_handle(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    username = update.effective_user.username or "NO_USERNAME"
    
    # Ignore group
    if chat_id < 0:
        return
    
    row_number, bg_color = await google_sheets.get_row_and_color(username, config.google_sheet_id)
    if not row_number:
        await context.bot.send_message(chat_id=chat_id, text=config.username_not_found_text.format(username), parse_mode = "HTML")
        return
    
    # checks that the backgroud is {'green': 1}
    if isinstance(bg_color, dict) and 'green' in bg_color and bg_color['green'] == 1 and len(bg_color) == 1:
        await context.bot.send_message(chat_id=chat_id, text=config.already_done_text, parse_mode = "HTML")
        return

    total_people, total_sum = await google_sheets.get_n_people_and_total_sum(config.google_sheet_id)
    geom_seq_a = total_sum*(1-config.GEOM_SEQ_R)/(1-config.GEOM_SEQ_R**total_people)
    
    sum_to_pay, count = await context.application.bot_data["db"].get_sum_to_pay_and_count(chat_id=chat_id, username=username, total_people=total_people, geom_seq_a=geom_seq_a, geom_seq_r=config.GEOM_SEQ_R)
    
    await context.bot.send_message(chat_id=chat_id, text=config.start_text.format(count+1, total_people, sum_to_pay, math.ceil(geom_seq_a), sum_to_pay, math.ceil(geom_seq_a*config.GEOM_SEQ_R**(total_people-1)), math.ceil(sum_to_pay*config.GEOM_SEQ_R), round((config.GEOM_SEQ_R-1)*100, 2)), parse_mode = "HTML")


async def post_init(application: Application) -> None:
    # Hide the default commands menu
    await application.bot.set_my_commands([])

    # Create the AsyncDatabase instance:
    db = await database.AsyncDatabase.create()

    application.bot_data["db"] = db


async def get_unique_chat_link(context: CallbackContext, group_chat_id: str) -> str: 
    """ 
    Create a single-use invite link to `group_chat_id`. 
 
    Parameters: 
    ----------- 
    context : CallbackContext
        The callback context containing the bot instance.
    chat_id : str 
        Unique identifier (or @username) of the target group/supergroup. 
 
    Returns: 
    -------- 
    invite_link : str 
        The invite URL which can be sent to the user. 
 
    Raises: 
    ------- 
    TelegramError 
        If the API call fails (e.g. bot is not an admin with invite rights). 
    """ 
    try: 
        invite = await context.bot.create_chat_invite_link( 
            chat_id=group_chat_id, 
            member_limit=1 
        )
        return invite.invite_link 
 
    except TelegramError as e: 
        # Handle errors (e.g. lack of permissions, invalid chat_id, etc.) 
        raise RuntimeError(f"Failed to create invite link: {e.message}")


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
        row_number, bg_color = await google_sheets.get_row_and_color(username, config.google_sheet_id)

        if row_number:
            # checks that the backgroud not {'green': 1}
            if not (isinstance(bg_color, dict) and 'green' in bg_color and bg_color['green'] == 1 and len(bg_color) == 1):
                unique_invite_link = await get_unique_chat_link(context=context, group_chat_id=config.group_chat_id)
                
                count, sum_to_pay, elapsed_interval = await context.application.bot_data["db"].insert_check_link(
                    chat_id=chat_id,
                    check_link=file_url,
                    check_file_id=file_id,
                )
                
                await google_sheets.color_row_and_insert_data(row_number, count, sum_to_pay, elapsed_interval, config.google_sheet_id)
                
                for alert_chat_id in config.telegram_alerts_chats:
                    await context.bot.send_photo(
                        chat_id=alert_chat_id,
                        photo=file_id,
                        caption=config.alert_text.format(count+1, username, sum_to_pay),
                        parse_mode="HTML"
                    )
                
                await context.bot.send_message(chat_id=chat_id, text=config.success_text.format(unique_invite_link, row_number), parse_mode = "HTML")
            else: # already green in the table
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