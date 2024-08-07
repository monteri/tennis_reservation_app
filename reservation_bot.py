import os
import django
import requests

# Set the settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tennis_reservation_app.settings')
django.setup()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler, ConversationHandler, MessageHandler, filters
from datetime import datetime, timedelta, time
from asgiref.sync import sync_to_async
from app.models import Reservation, AdminSession
from django.conf import settings

# States for conversation
DURATION_SELECTION, DATE_SELECTION, TIME_SELECTION, NAME_PHONE, CONFIRMATION = range(5)

async def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Забронювати", callback_data='start_reservation')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Вас вітає Tennis bot. Ви можете забронювати стіл на бажаний час.",
        reply_markup=reply_markup
    )

async def start_reservation(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    durations = [
        ("1 година - 250₴", "60"),
        ("1,5 години - 375₴", "90"),
        ("2 години - 475₴ (5% знижка)", "120"),
        ("3 години - 675₴ (10% знижка)", "180"),
    ]

    keyboard = [[InlineKeyboardButton(text, callback_data=value)] for text, value in durations]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "Оберіть тривалість:",
        reply_markup=reply_markup
    )
    return DURATION_SELECTION

async def select_date(update: Update, context: CallbackContext):
    query = update.callback_query

    if query.data == 'back_to_duration':  # Handle back to duration selection
        await start_reservation(update, context)
        return DURATION_SELECTION

    await query.answer()

    if query.data != 'back_to_date':
        context.user_data['reservation_duration'] = int(query.data)

    today = datetime.today()
    dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(14)]

    keyboard = [[InlineKeyboardButton(date, callback_data=date)] for date in dates]
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='back_to_duration')])  # Back button
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "Оберіть дату (максимум 2 тижні у майбутньому):",
        reply_markup=reply_markup
    )
    return DATE_SELECTION


@sync_to_async
def get_reserved_times(date_str):
    # Convert the string to a datetime.date object
    date = datetime.strptime(date_str, "%Y-%m-%d").date()

    reservations = Reservation.objects.filter(start_date=date)
    reserved_times = []
    for reservation in reservations:
        # Convert reservation.start_time (which is a time object) to a datetime object
        start_datetime = datetime.combine(date, reservation.start_time)
        end_datetime = start_datetime + timedelta(minutes=reservation.duration)
        reserved_times.append((start_datetime.time(), end_datetime.time()))
    return reserved_times

async def select_time(update: Update, context: CallbackContext):
    query = update.callback_query

    # Handle back navigation
    if query.data == 'back_to_date':  # Handle back to date selection
        return await select_date(update, context)  # Return to date selection
    elif query.data == 'back_to_duration':  # Handle back to duration selection
        return await start_reservation(update, context)  # Return to duration selection

    await query.answer()

    # Parse the selected date
    context.user_data['reservation_date'] = query.data
    duration = context.user_data['reservation_duration']

    selected_date = datetime.strptime(context.user_data['reservation_date'], "%Y-%m-%d").date()
    today = datetime.today().date()

    if selected_date == today:
        now = datetime.now()
        # Calculate the next half-hour slot
        minutes = (now.minute // 30 + 1) * 30
        if minutes == 60:
            now = now.replace(hour=now.hour + 1, minute=0)
        else:
            now = now.replace(minute=minutes)

        earliest_time = max(now.hour * 60 + now.minute, 9 * 60)  # Start at 9:00 AM or the current time
    else:
        earliest_time = 9 * 60  # Start at 9:00 AM

    latest_start_time = 23 * 60 - duration  # Calculate the latest possible start time in minutes

    reserved_times = await get_reserved_times(context.user_data['reservation_date'])

    available_times = []
    for time_in_minutes in range(earliest_time, latest_start_time + 1, 30):
        hours = time_in_minutes // 60
        minutes = time_in_minutes % 60
        proposed_start = time(hours, minutes)
        proposed_end = (datetime.combine(selected_date, proposed_start) + timedelta(minutes=duration)).time()

        overlap = any(start <= proposed_start < end or start < proposed_end <= end for start, end in reserved_times)

        if not overlap:
            available_times.append(f"{hours:02d}:{minutes:02d}")

    if not available_times:
        await query.edit_message_text("На вибрану дату немає доступних часових слотів.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(time, callback_data=time)] for time in available_times]
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='back_to_date')])  # Back button to date selection
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"Оберіть час для {context.user_data['reservation_date']}:",
        reply_markup=reply_markup
    )
    return TIME_SELECTION


async def back_to_time_selection(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    duration = context.user_data['reservation_duration']
    selected_date = context.user_data['reservation_date']

    # Recalculate available times
    latest_start_time = 23 * 60 - duration
    reserved_times = await get_reserved_times(selected_date)

    available_times = []
    for time_in_minutes in range(9 * 60, latest_start_time + 1, 30):
        hours = time_in_minutes // 60
        minutes = time_in_minutes % 60
        proposed_start = time(hours, minutes)
        proposed_end = (
            datetime.combine(datetime.strptime(selected_date, "%Y-%m-%d").date(), proposed_start) + timedelta(
                minutes=duration)).time()

        overlap = any(start <= proposed_start < end or start < proposed_end <= end for start, end in reserved_times)

        if not overlap:
            available_times.append(f"{hours:02d}:{minutes:02d}")

    keyboard = [[InlineKeyboardButton(time, callback_data=time)] for time in available_times]
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='back_to_date')])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"Оберіть час для {selected_date}:",
        reply_markup=reply_markup
    )
    return TIME_SELECTION

async def collect_name_phone(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == 'back_to_time_selection':  # Handle back to time selection
        return await back_to_time_selection(update, context)
    elif query.data == 'back_to_date':  # Handle back to date selection
        return await select_date(update, context)

    context.user_data['reservation_time'] = query.data

    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data='back_to_time_selection')]  # Back button to time selection
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "Будь ласка, введіть ваше імʼя та номер телефону через кому (Наприклад: Андрій Шевченко, +380501234567):",
        reply_markup=reply_markup
    )
    return NAME_PHONE

@sync_to_async
def create_reservation(date, time, duration, name, username, phone):
    return Reservation.objects.create(
        start_date=date,
        start_time=time,
        duration=duration,
        name=name,
        username=username,
        phone=phone
    )

async def confirm_reservation(update: Update, context: CallbackContext):
    user_input = update.message.text
    try:
        name, phone = [x.strip() for x in user_input.split(',')]
        username = update.message.from_user.username

        reservation = await create_reservation(
            context.user_data['reservation_date'],
            context.user_data['reservation_time'],
            context.user_data['reservation_duration'],
            name,
            username,
            phone
        )

        await update.message.reply_text(
            "Ваше бронювання буде оброблене адміністратором та з вами зʼяжуться."
        )

        # Notify admin bot
        await notify_admins(reservation.id, name, context.user_data['reservation_date'], context.user_data['reservation_time'], context.user_data['reservation_duration'], phone, username)

    except ValueError:
        await update.message.reply_text(
            "Неправильний формат. Будь ласка, введіть ваше імʼя та номер телефону через кому."
        )
        return NAME_PHONE

    return ConversationHandler.END

@sync_to_async
def get_admin_sessions():
    return list(AdminSession.objects.values_list('chat_id', flat=True))

async def notify_admins(reservation_id, name, date, time, duration, phone, username):
    message = f"Нове бронювання від {name} на {date} о {time} на {duration // 60} години. Телефон: {phone}. Telegram: @{username}"

    keyboard = [
        [InlineKeyboardButton("Confirm", callback_data=f'confirm_{reservation_id}'),
         InlineKeyboardButton("Cancel", callback_data=f'cancel_{reservation_id}')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    admin_sessions = await get_admin_sessions()

    for chat_id in admin_sessions:
        try:
            requests.post(
                url=f"https://api.telegram.org/bot{settings.ADMIN_BOT_TOKEN}/sendMessage",
                data={"chat_id": chat_id, "text": message, "reply_markup": reply_markup.to_json()},
            )
        except Exception as e:
            print(f"Error notifying admin {chat_id}: {e}")

async def cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("Процес бронювання скасовано. @!#")
    return ConversationHandler.END

if __name__ == '__main__':
    application = Application.builder().token(settings.RESERVATION_BOT_TOKEN).build()

    start_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_reservation, pattern='start_reservation')],
        states={
            DURATION_SELECTION: [CallbackQueryHandler(select_date)],
            DATE_SELECTION: [CallbackQueryHandler(select_time)],
            TIME_SELECTION: [
                CallbackQueryHandler(collect_name_phone),
                CallbackQueryHandler(select_date, pattern='back_to_date')
            ],
            NAME_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_reservation),
                CallbackQueryHandler(back_to_time_selection, pattern='back_to_time_selection')
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_chat=True,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(start_conv_handler)

    application.run_polling()
