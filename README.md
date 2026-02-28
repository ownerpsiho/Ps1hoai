# 🤖 Gemini AI Bot — Production Ready

Полноценный Telegram бот на базе **Google Gemini AI** с PostgreSQL, генерацией изображений и распознаванием голоса.

---

## ✨ Возможности

| Функция | Описание |
|---|---|
| 💬 AI Чат | Умный диалог с Gemini 2.0 Flash / Pro, контекст до 100 сообщений |
| 🖼 Анализ фото | Gemini Vision — описание и анализ любых изображений |
| 🎙 Голосовые | Автоматическая транскрипция через Gemini |
| 📄 Документы | Анализ PDF, TXT, CSV, JSON до 10 МБ |
| 🎨 Генерация картинок | FLUX через Together AI, 8 стилей, 5 размеров |
| 🧠 Персонажи AI | 8 режимов: Стандартный, Программист, Творческий, Аналитик... |
| 📋 Пресеты | Свои системные промпты для каждого пользователя |
| 💎 Подписки | 4 тарифа с дневными лимитами (Free / Basic / Pro / Unlimited) |
| 👥 Рефералы | Реферальная система с бонусными сообщениями |
| 📢 Рассылки | Рассылка всем или по тарифу |
| 🚫 Бан-система | Бан/разбан пользователей с причиной |
| 📊 Статистика | Детальная аналитика по пользователям и тарифам |

---

## 🚀 Деплой на Railway (самый простой способ)

1. Форкни репозиторий на GitHub
2. Зайди на [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Добавь **PostgreSQL** сервис (Railway создаёт `DATABASE_URL` автоматически)
4. Заполни переменные окружения (Variables):

```
BOT_TOKEN       = токен от @BotFather
GEMINI_KEY      = ключ с aistudio.google.com
ADMIN_IDS       = твой Telegram ID
IMAGEGEN_KEY    = ключ с api.together.xyz (для картинок)
OWNER_USERNAME  = @твой_ник
CHANNEL_LINK    = https://t.me/канал
```

5. Deploy! Всё, бот работает 🎉

---

## 🐳 Локальный запуск через Docker

```bash
# 1. Клонируй и настрой
cp .env.example .env
nano .env  # заполни переменные

# 2. Запусти (PostgreSQL + бот)
docker-compose up -d

# 3. Логи
docker-compose logs -f bot
```

### docker-compose.yml

```yaml
version: '3.8'
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: gemini_bot
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - pgdata:/var/lib/postgresql/data

  bot:
    build: .
    env_file: .env
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@db/gemini_bot
    depends_on:
      - db
    restart: unless-stopped

volumes:
  pgdata:
```

---

## 💻 Ручной запуск

```bash
# Python 3.12+
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt

# Настрой переменные
cp .env.example .env
# заполни .env

# Запуск
python main.py
```

---

## 📁 Структура проекта

```
gemini_bot/
├── main.py                  # точка входа, настройка бота
├── requirements.txt
├── Dockerfile
├── .env.example
│
├── config/
│   └── settings.py          # все настройки и тарифы PLANS
│
├── database/
│   ├── models.py            # SQLAlchemy модели (User, Message, ...)
│   ├── connection.py        # engine, сессии, init_db
│   └── repository.py        # все операции с БД (UserRepo, MessageRepo, ...)
│
├── services/
│   ├── gemini.py            # Gemini API (chat, vision, STT)
│   └── imagegen.py          # Together AI (FLUX) + gTTS
│
├── handlers/
│   ├── commands.py          # /start, /help, /new, /stats, /image, /ref
│   ├── chat.py              # основной AI чат, фото, голос, документы
│   ├── callbacks.py         # все inline-кнопки (меню, настройки, ...)
│   ├── image.py             # FSM генерации изображений
│   └── admin.py             # полная админ-панель
│
├── middlewares/
│   └── __init__.py          # UserMiddleware, RateLimit, Logging, BanCheck
│
├── keyboards/
│   └── __init__.py          # все клавиатуры бота
│
└── utils/
    └── __init__.py          # форматирование, escape_html, progress_bar, ...
```

---

## 💎 Тарифы

| Тариф | Сообщений/день | Картинок/день | Голосовых/день | Цена |
|---|---|---|---|---|
| 🆓 Бесплатный | 10 | 2 | 5 | Бесплатно |
| ⚡ Базовый | 50 | 10 | 20 | $3/мес |
| 🔥 Pro | 200 | 30 | 50 | $8/мес |
| 👑 Безлимит | ∞ | ∞ | ∞ | $15/мес |

Выдача подписок — через админ-панель (`/admin` → Выдать подписку).

---

## ⚙️ Получение API ключей

**Gemini API (обязательно)**
1. [aistudio.google.com](https://aistudio.google.com)
2. Get API key → Create API key
3. Бесплатный лимит: 1500 запросов/день

**Together AI для картинок (опционально)**
1. [api.together.xyz](https://api.together.xyz)
2. Регистрация → API Keys → Create
3. $1 стартовый кредит, FLUX.1-schnell бесплатен

---

## 🛠 Настройка тарифов

Тарифы в `config/settings.py` → словарь `PLANS`. Можно добавить свои:

```python
PLANS = {
    "vip": {
        "name": "⭐ VIP",
        "emoji": "⭐",
        "daily_limit": 500,
        "image_limit": 50,
        "voice_limit": 100,
        "price": 20,
        "price_rub": 1990,
        "history": 80,
        "desc": "500 сообщений/день · 20$/мес",
        "features": ["✅ Gemini Pro", "✅ 500 сообщений/день"],
    }
}
```
