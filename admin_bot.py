import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tennis_reservation_app.settings')
django.setup()

from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler
from app.models import Reservation, Admin, AdminSession
from django.contrib.auth.hashers import check_password
from django.conf import settings
from asgiref.sync import sync_to_async

@sync_to_async
def verify_login(username, password):
    try:
        admin = Admin.objects.get(username=username)
        if check_password(password, admin.password):
            return admin.id
    except Admin.DoesNotExist:
        return None

@sync_to_async
def delete_reservation(reservation_id):
    try:
        reservation = Reservation.objects.get(id=reservation_id)
        reservation.delete()
        return True
    except Reservation.DoesNotExist:
        return False

@sync_to_async
def confirm_reservation_by_id(reservation_id):
    try:
        reservation = Reservation.objects.get(id=reservation_id)
        reservation.confirmed = True
        reservation.save()
        return True
    except Reservation.DoesNotExist:
        return False

@sync_to_async
def create_admin_session(chat_id):
    return AdminSession.objects.get_or_create(chat_id=chat_id)

@sync_to_async
def get_admin_sessions():
    return AdminSession.objects.all()

async def login(update: Update, context: CallbackContext):
    if len(context.args) != 2:
        await update.message.reply_text('Usage: /login <username> <password>')
        return

    username, password = context.args
    admin_id = await verify_login(username, password)
    if admin_id:
        context.user_data['admin_logged_in'] = True
        await create_admin_session(update.effective_chat.id)
        await update.message.reply_text('Login successful!')
    else:
        await update.message.reply_text('Login failed. Invalid credentials.')

async def cancel_reservation(update: Update, context: CallbackContext):
    if 'admin_logged_in' not in context.user_data or not context.user_data['admin_logged_in']:
        await update.message.reply_text('Please log in first using /login.')
        return

    reservation_id = context.args[0]
    success = await delete_reservation(reservation_id)
    if success:
        await update.message.reply_text(f'Reservation {reservation_id} has been cancelled.')
    else:
        await update.message.reply_text(f'Reservation {reservation_id} not found.')

async def confirm_reservation(update: Update, context: CallbackContext):
    if 'admin_logged_in' not in context.user_data or not context.user_data['admin_logged_in']:
        await update.message.reply_text('Please log in first using /login.')
        return

    reservation_id = context.args[0]
    success = await confirm_reservation_by_id(reservation_id)
    if success:
        await update.message.reply_text(f'Reservation {reservation_id} has been confirmed.')
    else:
        await update.message.reply_text(f'Reservation {reservation_id} not found.')

async def handle_callback_query(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data.split('_')

    if data[0] == 'confirm':
        reservation_id = int(data[1])
        success = await confirm_reservation_by_id(reservation_id)
        if success:
            await query.answer('Reservation confirmed.')
            await query.edit_message_text(f'Reservation {reservation_id} has been confirmed.')
        else:
            await query.answer('Reservation not found.')
    elif data[0] == 'cancel':
        reservation_id = int(data[1])
        success = await delete_reservation(reservation_id)
        if success:
            await query.answer('Reservation canceled.')
            await query.edit_message_text(f'Reservation {reservation_id} has been canceled.')
        else:
            await query.answer('Reservation not found.')

if __name__ == '__main__':
    application = Application.builder().token(settings.ADMIN_BOT_TOKEN).build()

    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("cancel", cancel_reservation))
    application.add_handler(CommandHandler("confirm", confirm_reservation))
    application.add_handler(CallbackQueryHandler(handle_callback_query))  # For handling button presses

    application.run_polling()
