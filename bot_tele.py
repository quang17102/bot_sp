# -*- coding: utf-8 -*-
"""
Main file cho Telegram Bot
Ch\u1EE9a job queue setup v\u00E0 bot initialization
"""

from telegram.ext import ApplicationBuilder
from job_queue import JobQueue
from workers import handle_cvc, handle_cks, handle_checkmail, handle_mailfree, handle_newmail, handle_qr
from commands import setup_commands

# TOKEN = "8779407961:AAEmCsWPOpjUueWc7uH8HsDhwPfVcV4hjwY"
TOKEN = "8667315240:AAFj9GwaVWqYUUxGjxHQFwi9IaQodhVgjnA"


def main():
    """Kh\u1EDFi t\u1EA1o v\u00E0 ch\u1EA1y bot"""
    # Kh\u1EDFi t\u1EA1o Job Queue
    job_queue = JobQueue(max_workers=10)
    
    # \u0110\u0103ng k\u00FD worker handlers
    job_queue.register_handler("cvc", handle_cvc)
    job_queue.register_handler("cks", handle_cks)
    job_queue.register_handler("qr", handle_qr)
    job_queue.register_handler("checkmail", handle_checkmail)
    job_queue.register_handler("mailfree", handle_mailfree)
    job_queue.register_handler("newmail", handle_newmail)
    
    # Kh\u1EDFi \u0111\u1ED9ng workers
    job_queue.start_workers()
    
    # T\u1EA1o application v\u1EDBi token
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Set bot_app v\u00E0o job_queue \u0111\u1EC3 workers c\u00F3 th\u1EC3 g\u1EEDi message
    job_queue.set_bot_app(application)
    
    # \u0110\u0103ng k\u00FD t\u1EA5t c\u1EA3 command handlers
    setup_commands(application, job_queue)
    
    # Ch\u1EA1y bot
    print("Bot \u0111ang ch\u1EA1y...")
    print(f"Workers: {job_queue.max_workers}")
    print(f"Registered handlers: {list(job_queue.handlers.keys())}")
    application.run_polling()


if __name__ == "__main__":
    main()

