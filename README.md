# Telegram Bot

A production-ready Telegram bot built with Python, Aiogram 3.x, PostgreSQL, SQLAlchemy, and Alembic.

## Features

- **User Registration** — Auto-registers on /start with referral support
- **Force Join** — Blocks access until required channels are joined
- **Main Menu** — 8 core sections: Balance, Tasks, Create Task, Referral, Deposit, Withdraw, Statistics, Support
- **Admin Panel** — User management, channel management, task review, withdrawal approval, support tickets, broadcast
- **Referral System** — $5 bonus per successful referral
- **Task System** — Create and complete tasks for rewards
- **Wallet System** — Deposit and withdrawal with manual admin review

## Setup

### 1. Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Required:
- `BOT_TOKEN` — From @BotFather
- `ADMIN_IDS` — Comma-separated Telegram user IDs (e.g. `123456789,987654321`)
- `DATABASE_URL` — PostgreSQL connection string

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Database Setup

The bot auto-creates all tables on startup using SQLAlchemy.

For migrations with Alembic:
```bash
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

### 4. Run

```bash
python main.py
```

## Admin Commands

- `/admin` — Open admin panel
- `/addbalance <user_id> <amount>` — Adjust user balance
- `/add_channel` — Add a required channel
- `/broadcast <message>` — Send message to all users

## Project Structure

```
telegram-bot/
├── main.py               # Entry point
├── config.py             # Pydantic settings
├── requirements.txt
├── alembic.ini
├── database/
│   ├── models.py         # SQLAlchemy models
│   ├── engine.py         # DB engine & session
│   ├── queries.py        # All DB query helpers
│   └── alembic/          # Migrations
├── bot/
│   ├── filters/          # IsAdmin filter
│   ├── middlewares/      # DB session + Force Join
│   ├── keyboards/        # All keyboards
│   └── handlers/         # All message handlers
│       └── admin/        # Admin sub-handlers
└── utils/                # Helpers
```
