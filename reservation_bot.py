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

# Custom day names in Ukrainian
DAY_NAMES_UA = {
    'Monday': 'Понеділок',
    'Tuesday': 'Вівторок',
    'Wednesday': 'Середа',
    'Thursday': 'Четвер',
    'Friday': 'Пʼятниця',
    'Saturday': 'Субота',
    'Sunday': 'Неділя',
}

# Duration to price mapping
DURATION_TO_PRICE = {
    60: 300,   # 1 hour
    90: 450,   # 1.5 hours
    120: 550,  # 2 hours
    180: 750   # 3 hours
}

# States for conversation
DURATION_SELECTION, DATE_SELECTION, TIME_SELECTION, NAME_PHONE, CONFIRMATION = range(5)

async def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Забронювати 🏓", callback_data='start_reservation')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Вас вітає Tennis bot. Ви можете забронювати стіл на бажаний час.",
        reply_markup=reply_markup
    )

async def start_reservation(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    durations = [
        ("1 година - 300₴ ⏱️", "60"),
        ("1,5 години - 450₴ ⏱️", "90"),
        ("2 години - 550₴ ⏱️ (275 ₴/година)", "120"),
        ("3 години - 750₴ ⏱️ (250 ₴/година)", "180"),
    ]

    keyboard = [[InlineKeyboardButton(text, callback_data=value)] for text, value in durations]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "⏳ Оберіть тривалість:",
        reply_markup=reply_markup
    )
    return DURATION_SELECTION

def format_date_ua(date_obj, escaped=False):
    # Format date as "09.08, Пʼятниця"
    day_name = DAY_NAMES_UA[date_obj.strftime('%A')]
    date = date_obj.strftime(f'%d\.%m \({day_name}\)') if escaped else date_obj.strftime(f'%d.%m, {day_name}')
    return date

async def select_date(update: Update, context: CallbackContext):
    query = update.callback_query

    if query.data == 'back_to_duration':  # Handle back to duration selection
        await start_reservation(update, context)
        return DURATION_SELECTION

    await query.answer()

    if query.data != 'back_to_date':
        context.user_data['reservation_duration'] = int(query.data)

    today = datetime.today()
    dates = [(today + timedelta(days=i)) for i in range(14)]

    keyboard = []
    for date in dates:
        formatted_date = format_date_ua(date)
        callback_data = date.strftime("%Y-%m-%d")  # Use a standard date format for callback data
        keyboard.append([InlineKeyboardButton(formatted_date, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='back_to_duration')])  # Back button
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "📅 Оберіть дату (максимум 2 тижні у майбутньому):",
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
    formatted_date = format_date_ua(selected_date)
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
        await query.edit_message_text("⛔ На вибрану дату немає доступних часових слотів.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(time, callback_data=time)] for time in available_times]
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='back_to_date')])  # Back button to date selection
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"🕒 Оберіть час для {formatted_date}:",
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
        f"⏰ Оберіть час для {selected_date}:",
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
        "📞 Будь ласка, введіть ваші контактні дані (Наприклад: Андрій Шевченко, +380501234567, коментар):",
        reply_markup=reply_markup
    )
    return NAME_PHONE

@sync_to_async
def create_reservation(date, time_str, duration, text, username):
    # Convert date and time_str to datetime objects
    reservation_date = datetime.strptime(date, "%Y-%m-%d").date()
    reservation_time = datetime.strptime(time_str, "%H:%M").time()
    reservation_datetime = datetime.combine(reservation_date, reservation_time)

    # Check if the reservation datetime is in the past
    if reservation_datetime < datetime.now():
        return None, "⛔ Ви не можете забронювати на минулу дату або час."

    # Calculate end time of the new reservation
    new_end_time = (reservation_datetime + timedelta(minutes=duration)).time()

    # Fetch reservations on the same date to check for overlapping times
    existing_reservations = Reservation.objects.filter(start_date=reservation_date)

    for existing_reservation in existing_reservations:
        # Calculate the end time of the existing reservation
        existing_end_time = (datetime.combine(existing_reservation.start_date, existing_reservation.start_time) +
                             timedelta(minutes=existing_reservation.duration)).time()

        # Check for overlap: the start time of one is between the start and end of the other
        if (existing_reservation.start_time <= reservation_time < existing_end_time) or \
           (reservation_time <= existing_reservation.start_time < new_end_time):
            return None, "⛔ На цей час вже існує бронювання. Будь ласка, оберіть інший час."

    # If no overlaps and the date is valid, create the reservation
    reservation = Reservation.objects.create(
        start_date=reservation_date,
        start_time=reservation_time,
        duration=duration,
        text=text,
        username=username
    )

    return reservation, None

async def confirm_reservation(update: Update, context: CallbackContext):
    user_input = update.message.text
    try:
        text = user_input.strip()
        username = update.message.from_user.username

        # Get the selected duration
        duration = context.user_data['reservation_duration']
        # Determine the price based on the duration
        price = DURATION_TO_PRICE.get(duration, 0)  # Default to 0 if not found

        # Try to create the reservation
        reservation, error_message = await create_reservation(
            context.user_data['reservation_date'],
            context.user_data['reservation_time'],
            duration,
            text,
            username
        )

        if reservation is None:
            # If there was an error in reservation creation (like overlap or past datetime)
            await update.message.reply_text(error_message)
            return NAME_PHONE

        reservation_date = datetime.strptime(context.user_data['reservation_date'], '%Y-%m-%d')
        # If reservation was successfully created
        await update.message.reply_text(
            f"🏓 *Бронь столу*\n\n"
            f"📅 *Дата:* {format_date_ua(reservation_date, escaped=True)}\n"
            f"🕔 *Час:* {context.user_data['reservation_time']} \\- "
            f"{(datetime.strptime(context.user_data['reservation_time'], '%H:%M') + timedelta(minutes=duration)).strftime('%H:%M')}\n"
            f"💵 *До сплати:* {price} грн\n"
            "💳 *Карта:* 5169155116940766\n\n"
            "⏳ *Чекаємо на оплату впродовж 15\\-ти хвилин*\n\n"
            "✅ Після оплати чекайте на підтвердження від адміністратора \\(\\@nastilnyy\\_tenis\\)",
            parse_mode='MarkdownV2'
        )

        # Notify admin bot
        await notify_admins(reservation.id, context.user_data['reservation_date'], context.user_data['reservation_time'], duration, text, username)

    except ValueError:
        await update.message.reply_text(
            "⚠️ Неправильний формат. Будь ласка, введіть ваше імʼя та номер телефону через кому."
        )
        return NAME_PHONE

    return ConversationHandler.END

@sync_to_async
def get_admin_sessions():
    return list(AdminSession.objects.values_list('chat_id', flat=True))

async def notify_admins(reservation_id, date, time, duration, text, username):
    message = f"🔔 Нове бронювання на {date} о {time} на {duration / 60} години.\n"
    message += f"📋 Контактні дані: {text}\n"
    message += f"💬 Telegram: @{username}"

    keyboard = [
        [InlineKeyboardButton("✅ Confirm", callback_data=f'confirm_{reservation_id}'),
         InlineKeyboardButton("❌ Cancel", callback_data=f'cancel_{reservation_id}')]
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
    await update.message.reply_text("🚫 Процес бронювання скасовано.")
    return ConversationHandler.END


async def info(update: Update, context: CallbackContext) -> None:
    info_text = (
        "*УМОВИ та ПРАВИЛА*\n"
        "• Орендар залу повинен бути старше *16 років*.\n"
        "• Заборонено вживати алкогольні напої та перебувати у стані алкогольного або наркотичного спʼяніння.\n"
        "• Використання змінного взуття _обов'язкове_.\n"
        "• Орендар залу несе повну відповідальність за будь-які пошкодження, завдані ним або його опонентами.\n"
        "• Заборонено виконувати сальто та інші небезпечні трюки в приміщенні. "
        "За будь-які травми або ушкодження, отримані внаслідок недотримання правил, відповідальність несе особа, яка порушила ці правила.\n"
        "• Поважайте час наступного гравця та завершуйте гру заздалегідь.\n"
        "• Після гри покладіть інвентар на місце, вимкніть світло та зачиніть двері.\n\n"
        "*ШТРАФИ*\n"
        "• Роздавлений м'яч — *50 грн*.\n"
        "• Пошкоджена або зламана ракетка — від *250 грн* до *1000 грн* (залежно від ступеня пошкодження).\n"
        "• Якщо після вашого візиту приміщення потребує додаткового прибирання — *300 грн*.\n\n"
        "_Натискаючи кнопку «ЗАБРОНЮВАТИ СТІЛ», ви погоджуєтесь із нашими правилами відвідування залу._"
    )
    await update.message.reply_text(info_text, parse_mode='Markdown')


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

    # Add the /info command handler
    application.add_handler(CommandHandler("info", info))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(start_conv_handler)

    application.run_polling()