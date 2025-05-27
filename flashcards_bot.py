import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, 
    CallbackContext, CallbackQueryHandler, ConversationHandler
)
import pandas as pd

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
ADD_QUESTION, ADD_ANSWER = range(2)
REVIEW_CARD, SHOW_ANSWER = range(2)
EDIT_CHOOSE, EDIT_QUESTION, EDIT_ANSWER = range(3)

def edit_flashcard_start(update: Update, context: CallbackContext) -> int:
    """Начинает процесс редактирования флешкарты"""
    user_id = update.effective_user.id
    user_cards = bot.get_user_cards(user_id)
    
    if user_cards.empty:
        update.message.reply_text("У вас пока нет флешкарт для редактирования.")
        return ConversationHandler.END
    
    # Создаем клавиатуру с карточками
    keyboard = [
        [InlineKeyboardButton(f"{idx+1}. {row['question']}", callback_data=f"edit_{idx}")]
        for idx, row in user_cards.iterrows()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        "Выберите флешкарту для редактирования:",
        reply_markup=reply_markup
    )
    return EDIT_CHOOSE

def edit_flashcard_choose(update: Update, context: CallbackContext) -> int:
    """Обрабатывает выбор карточки для редактирования"""
    query = update.callback_query
    query.answer()
    
    card_idx = int(query.data.split('_')[1])
    context.user_data['edit_idx'] = card_idx
    
    query.edit_message_text(
        "Введите новый вопрос (или /skip чтобы оставить текущий):"
    )
    return EDIT_QUESTION

def edit_flashcard_question(update: Update, context: CallbackContext) -> int:
    """Получает новый вопрос"""
    if update.message.text.lower() != '/skip':
        context.user_data['new_question'] = update.message.text
    
    update.message.reply_text(
        "Введите новый ответ (или /skip чтобы оставить текущий):"
    )
    return EDIT_ANSWER

def edit_flashcard_answer(update: Update, context: CallbackContext) -> int:
    """Получает новый ответ и сохраняет изменения"""
    user_id = update.effective_user.id
    card_idx = context.user_data['edit_idx']
    
    # Получаем текущую карточку
    user_cards = bot.get_user_cards(user_id)
    card = user_cards.iloc[card_idx]
    
    # Обновляем данные
    new_question = context.user_data.get('new_question', card['question'])
    new_answer = update.message.text if update.message.text.lower() != '/skip' else card['answer']
    
    # Обновляем в DataFrame - ВНИМАНИЕ НА СКОБКИ!
    mask = ((bot.df['user_id'] == user_id) & 
            (bot.df['question'] == card['question']) & 
            (bot.df['answer'] == card['answer']))
    
    bot.df.loc[mask, ['question', 'answer']] = [new_question, new_answer]
    
    bot.save_flashcards()
    
    update.message.reply_text(
        "Флешкарта успешно обновлена!\n\n"
        f"Новый вопрос: {new_question}\n"
        f"Новый ответ: {new_answer}"
    )
    return ConversationHandler.END

def about_command(update: Update, context: CallbackContext) -> None:
    """Обработчик команды /about"""
    about_text = """
<b>📚 Flashcard Bot</b> - умный помощник для запоминания корейских слов

<u>Основные возможности:</u>
• Создание флешкарт с вопросами и ответами
• Редактирование и удаление карточек
• Повторение карточек по категориям
• Простая система организации знаний

<u>Разработан студентами группы 04.1-302 ИМОИиВ КФУ:</u> 
Логинова М.А.
Березина А.Ф.
Ахметвалиева Л.Р.
Охват А.Д.
Юсупова Д.Ф.
Киселева Е.Е

    """
    update.message.reply_text(about_text, parse_mode='HTML', disable_web_page_preview=True)

DELETE_CHOOSE = range(1)

def delete_flashcard_start(update: Update, context: CallbackContext) -> int:
    """Начинает процесс удаления флешкарты"""
    user_id = update.effective_user.id
    user_cards = bot.get_user_cards(user_id)
    
    if user_cards.empty:
        update.message.reply_text("У вас пока нет флешкарт для удаления.")
        return ConversationHandler.END
    
    # Создаем клавиатуру с карточками
    keyboard = [
        [InlineKeyboardButton(f"{idx+1}. {row['question']}", callback_data=f"delete_{idx}")]
        for idx, row in user_cards.iterrows()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        "Выберите флешкарту для удаления:",
        reply_markup=reply_markup
    )
    return DELETE_CHOOSE

def delete_flashcard_confirm(update: Update, context: CallbackContext) -> int:
    """Подтверждает удаление карточки"""
    query = update.callback_query
    query.answer()
    
    card_idx = int(query.data.split('_')[1])
    user_id = update.effective_user.id
    user_cards = bot.get_user_cards(user_id)
    card = user_cards.iloc[card_idx]
    
    # Удаляем карточку
    bot.df = bot.df[~(bot.df['user_id'] == user_id) & 
                   (bot.df['question'] == card['question']) & 
                   (bot.df['answer'] == card['answer'])]
    
    bot.save_flashcards()
    
    query.edit_message_text(
        f"Флешкарта удалена:\n\nВопрос: {card['question']}\nОтвет: {card['answer']}"
    )
    return ConversationHandler.END

# Файл для хранения флешкарт
FLASHCARDS_FILE = 'flashcards.csv'

class FlashcardBot:
    def __init__(self):
        # Загружаем флешкарты из файла или создаем новый DataFrame
        try:
            self.df = pd.read_csv(FLASHCARDS_FILE)
        except FileNotFoundError:
            self.df = pd.DataFrame(columns=['user_id', 'question', 'answer', 'category'])
    
    def save_flashcards(self):
        """Сохраняет флешкарты в файл"""
        self.df.to_csv(FLASHCARDS_FILE, index=False)
    
    def add_flashcard(self, user_id, question, answer, category='default'):
        """Добавляет новую флешкарту"""
        new_card = pd.DataFrame({
            'user_id': [user_id],
            'question': [question],
            'answer': [answer],
            'category': [category]
        })
        self.df = pd.concat([self.df, new_card], ignore_index=True)
        self.save_flashcards()
    
    def get_user_cards(self, user_id, category=None):
        """Возвращает флешкарты пользователя"""
        user_cards = self.df[self.df['user_id'] == user_id]
        if category:
            user_cards = user_cards[user_cards['category'] == category]
        return user_cards
    
    def get_random_card(self, user_id, category=None):
        """Возвращает случайную флешкарту пользователя"""
        user_cards = self.get_user_cards(user_id, category)
        if not user_cards.empty:
            return user_cards.sample(1).iloc[0]
        return None

# Инициализация бота
bot = FlashcardBot()

def start(update: Update, context: CallbackContext) -> None:
    """Обработчик команды /start"""
    user = update.effective_user
    update.message.reply_text(
        f"Привет, {user.first_name}!\n\n"
        "Я бот для создания и изучения флешкарт.\n\n"
        "Доступные команды:\n"
        "/add - добавить новую флешкарту\n"
        "/edit - изменить существующую флеш-карту\n"
        "/delete - удалить флеш-карту\n"
        "/review - начать повторение флешкарт\n"
        "/list - показать все мои флешкарты\n"
        "/categories - показать все категории\n"
        "/about - информация о боте\n"
        "/help - справка по использованию бота"
    )

def help_command(update: Update, context: CallbackContext) -> None:
    """Обработчик команды /help"""
    update.message.reply_text(
        "Как использовать бота:\n\n"
        "/add - добавить новую флеш-карту\n"
        "/edit - изменить существующую флеш-карту\n"
        "/delete - удалить флеш-карту\n"
        "/review - начать повторение флеш-карт\n"
        "/list - показать все ваши флеш-карты\n"
        "/categories - показать все категории\n"
        "/about - информация о боте\n"
        "/help - справка\n"
        "Вы можете добавлять флешкарты в разные категории, указав категорию после вопроса через знак |, например: вопрос | категория, ответ \n"
    )

def add_flashcard_start(update: Update, context: CallbackContext) -> int:
    """Начинает процесс добавления флешкарты"""
    update.message.reply_text(
        "Введите вопрос для новой флешкарты:"
    )
    return ADD_QUESTION

def add_flashcard_question(update: Update, context: CallbackContext) -> int:
    """Получает вопрос и запрашивает ответ"""
    context.user_data['question'] = update.message.text
    update.message.reply_text(
        "Теперь введите ответ на этот вопрос:"
    )
    return ADD_ANSWER

def add_flashcard_answer(update: Update, context: CallbackContext) -> int:
    """Получает ответ и сохраняет флешкарту"""
    answer = update.message.text
    question = context.user_data['question']
    user_id = update.effective_user.id
    
    # Проверяем, есть ли категория (разделитель |)
    if '|' in question:
        question, category = [part.strip() for part in question.split('|', 1)]
    elif '|' in answer:
        answer, category = [part.strip() for part in answer.split('|', 1)]
    else:
        category = 'default'
    
    bot.add_flashcard(user_id, question, answer, category)
    update.message.reply_text(
        f"Флешкарта добавлена!\n\n"
        f"Вопрос: {question}\n"
        f"Ответ: {answer}\n"
        f"Категория: {category}"
    )
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext) -> int:
    """Отменяет текущую операцию"""
    update.message.reply_text('Операция отменена.')
    return ConversationHandler.END

def list_flashcards(update: Update, context: CallbackContext) -> None:
    """Показывает все флешкарты пользователя"""
    user_id = update.effective_user.id
    user_cards = bot.get_user_cards(user_id)
    
    if user_cards.empty:
        update.message.reply_text("У вас пока нет флешкарт.")
        return
    
    response = "Ваши флешкарты:\n\n"
    for idx, row in user_cards.iterrows():
        response += f"{idx+1}. Вопрос: {row['question']}\nОтвет: {row['answer']}\nКатегория: {row['category']}\n\n"
    
    update.message.reply_text(response[:4000])  # Ограничение Telegram на длину сообщения

def list_categories(update: Update, context: CallbackContext) -> None:
    """Показывает все категории пользователя"""
    user_id = update.effective_user.id
    user_cards = bot.get_user_cards(user_id)
    
    if user_cards.empty:
        update.message.reply_text("У вас пока нет флешкарт.")
        return
    
    categories = user_cards['category'].unique()
    response = "Ваши категории:\n\n" + "\n".join(categories)
    update.message.reply_text(response)

def review_start(update: Update, context: CallbackContext) -> int:
    """Начинает процесс повторения флешкарт"""
    user_id = update.effective_user.id
    context.user_data['category'] = None
    
    # Проверяем, есть ли у пользователя флешкарты
    if bot.get_user_cards(user_id).empty:
        update.message.reply_text("У вас пока нет флешкарт для повторения.")
        return ConversationHandler.END
    
    # Создаем клавиатуру с категориями
    categories = bot.get_user_cards(user_id)['category'].unique()
    if len(categories) > 1:
        keyboard = [
            [InlineKeyboardButton(cat, callback_data=f"review_{cat}")] 
            for cat in categories
        ]
        keyboard.append([InlineKeyboardButton("Все категории", callback_data="review_all")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(
            "Выберите категорию для повторения:",
            reply_markup=reply_markup
        )
        return REVIEW_CARD
    else:
        return show_next_card(update, context)

def review_category(update: Update, context: CallbackContext) -> int:
    """Обрабатывает выбор категории для повторения"""
    query = update.callback_query
    query.answer()
    
    category = query.data.split('_')[1]
    if category == 'all':
        context.user_data['category'] = None
    else:
        context.user_data['category'] = category
    
    query.edit_message_text(
        text=f"Выбрана категория: {category if category != 'all' else 'Все категории'}"
    )
    return show_next_card(update, context)

def show_next_card(update: Update, context: CallbackContext) -> int:
    """Показывает следующую флешкарту"""
    user_id = update.effective_user.id
    category = context.user_data.get('category')
    
    card = bot.get_random_card(user_id, category)
    if card is None:
        if update.callback_query:
            update.callback_query.edit_message_text("Нет флешкарт для повторения.")
        else:
            update.message.reply_text("Нет флешкарт для повторения.")
        return ConversationHandler.END
    
    context.user_data['current_card'] = card.to_dict()
    
    if update.callback_query:
        update.callback_query.edit_message_text(
            f"Вопрос:\n\n{card['question']}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Показать ответ", callback_data="show_answer")]
            ])
        )
    else:
        update.message.reply_text(
            f"Вопрос:\n\n{card['question']}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Показать ответ", callback_data="show_answer")]
            ])
        )
    
    return SHOW_ANSWER

def show_answer(update: Update, context: CallbackContext) -> int:
    """Показывает ответ на текущую флешкарту"""
    query = update.callback_query
    query.answer()
    
    card = context.user_data['current_card']
    
    query.edit_message_text(
        f"Вопрос:\n\n{card['question']}\n\n"
        f"Ответ:\n\n{card['answer']}\n\n"
        f"Категория: {card['category']}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Следующая карта", callback_data="next_card")]
        ])
    )
    
    return REVIEW_CARD

def main() -> None:
    """Запуск бота"""
    updater = Updater(TOKEN)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("about", about_command))

    # Обработчики команд
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("list", list_flashcards))
    dispatcher.add_handler(CommandHandler("categories", list_categories))
    
    # Обработчик добавления флешкарты
    add_handler = ConversationHandler(
        entry_points=[CommandHandler('add', add_flashcard_start)],
        states={
            ADD_QUESTION: [MessageHandler(Filters.text & ~Filters.command, add_flashcard_question)],
            ADD_ANSWER: [MessageHandler(Filters.text & ~Filters.command, add_flashcard_answer)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    dispatcher.add_handler(add_handler)
    
    # Обработчик редактирования флешкарты
    edit_handler = ConversationHandler(
        entry_points=[CommandHandler('edit', edit_flashcard_start)],
        states={
            EDIT_CHOOSE: [CallbackQueryHandler(edit_flashcard_choose, pattern="^edit_")],
            EDIT_QUESTION: [MessageHandler(Filters.text & ~Filters.command, edit_flashcard_question)],
            EDIT_ANSWER: [MessageHandler(Filters.text & ~Filters.command, edit_flashcard_answer)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    dispatcher.add_handler(edit_handler)
    
    # Обработчик удаления флешкарты
    delete_handler = ConversationHandler(
        entry_points=[CommandHandler('delete', delete_flashcard_start)],
        states={
            DELETE_CHOOSE: [CallbackQueryHandler(delete_flashcard_confirm, pattern="^delete_")],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    dispatcher.add_handler(delete_handler)
    
    # Обработчик повторения флешкарт
    review_handler = ConversationHandler(
        entry_points=[CommandHandler('review', review_start)],
        states={
            REVIEW_CARD: [
                CallbackQueryHandler(review_category, pattern="^review_"),
                CallbackQueryHandler(show_next_card, pattern="^next_card"),
            ],
            SHOW_ANSWER: [
                CallbackQueryHandler(show_answer, pattern="^show_answer"),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    dispatcher.add_handler(review_handler)
    
    # Запускаем бота
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()