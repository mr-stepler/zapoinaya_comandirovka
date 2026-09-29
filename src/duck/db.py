import os
import hashlib
import secrets
import sqlite3
from typing import Optional, Dict, Any, List

# Original MySQL Database Configuration
DB_CONFIG = {
    "host": "185.114.247.43",
    "port": 3306,
    "database": "sch688_vvedenie",
    "user": "sch688_vvedenie",
    "password": "Qwerty123",
    "connection_timeout": 5
}

SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "neuroapi.db")

_use_mysql = None

def get_mysql_connection():
    try:
        import mysql.connector
        cnx = mysql.connector.connect(**DB_CONFIG)
        if cnx.is_connected():
            return cnx
    except Exception:
        return None
    return None

def is_mysql_available() -> bool:
    global _use_mysql
    if _use_mysql is not None:
        return _use_mysql
    cnx = get_mysql_connection()
    if cnx:
        _use_mysql = True
        cnx.close()
    else:
        _use_mysql = False
    return _use_mysql

def get_db():
    if is_mysql_available():
        cnx = get_mysql_connection()
        if cnx:
            return "mysql", cnx
    
    # Fallback SQLite
    os.makedirs(os.path.dirname(SQLITE_PATH), exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return "sqlite", conn

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def generate_api_key() -> str:
    random_part = secrets.token_hex(20)
    return f"sk-neuro-{random_part}"

def init_db():
    db_type, conn = get_db()
    
    if db_type == "mysql":
        try:
            cur = conn.cursor(dictionary=True)
            
            # Ensure users table exists with all needed fields
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `users` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `username` VARCHAR(255) NOT NULL,
                `email` VARCHAR(255) NOT NULL UNIQUE,
                `password_hash` VARCHAR(255) NOT NULL,
                `balance` DOUBLE NOT NULL DEFAULT 150.0,
                `total_spent` DOUBLE NOT NULL DEFAULT 0.0,
                `total_deposited` DOUBLE NOT NULL DEFAULT 0.0,
                `tier` VARCHAR(50) DEFAULT 'Developer',
                `avatar_color` VARCHAR(20) DEFAULT '#6366f1',
                `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            
            # Check if columns balance etc exist in users, if not add them
            cur.execute("DESCRIBE `users`")
            existing_cols = [row['Field'] for row in cur.fetchall()]
            
            if 'balance' not in existing_cols:
                try: cur.execute("ALTER TABLE `users` ADD COLUMN `balance` DOUBLE NOT NULL DEFAULT 150.0")
                except Exception: pass
            if 'total_spent' not in existing_cols:
                try: cur.execute("ALTER TABLE `users` ADD COLUMN `total_spent` DOUBLE NOT NULL DEFAULT 0.0")
                except Exception: pass
            if 'total_deposited' not in existing_cols:
                try: cur.execute("ALTER TABLE `users` ADD COLUMN `total_deposited` DOUBLE NOT NULL DEFAULT 0.0")
                except Exception: pass
            if 'tier' not in existing_cols:
                try: cur.execute("ALTER TABLE `users` ADD COLUMN `tier` VARCHAR(50) DEFAULT 'Developer'")
                except Exception: pass
            if 'avatar_color' not in existing_cols:
                try: cur.execute("ALTER TABLE `users` ADD COLUMN `avatar_color` VARCHAR(20) DEFAULT '#6366f1'")
                except Exception: pass
            if 'created_at' not in existing_cols:
                try: cur.execute("ALTER TABLE `users` ADD COLUMN `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                except Exception: pass

            cur.execute("""
            CREATE TABLE IF NOT EXISTS `api_keys` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `user_id` INT NOT NULL,
                `name` VARCHAR(255) NOT NULL,
                `key_hash` VARCHAR(255) NOT NULL,
                `key_prefix` VARCHAR(255) NOT NULL,
                `spend_limit` DOUBLE DEFAULT 0.0,
                `spent` DOUBLE DEFAULT 0.0,
                `is_active` INT DEFAULT 1,
                `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                `last_used_at` TIMESTAMP NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS `transactions` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `user_id` INT NOT NULL,
                `amount` DOUBLE NOT NULL,
                `type` VARCHAR(50) NOT NULL,
                `payment_method` VARCHAR(50) NULL,
                `description` TEXT NOT NULL,
                `status` VARCHAR(50) DEFAULT 'success',
                `reference_id` VARCHAR(100) NULL,
                `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS `models` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `slug` VARCHAR(100) NOT NULL UNIQUE,
                `name` VARCHAR(255) NOT NULL,
                `provider` VARCHAR(100) NOT NULL,
                `category` VARCHAR(50) NOT NULL,
                `price_input_1m` DOUBLE NOT NULL,
                `price_output_1m` DOUBLE NOT NULL,
                `context_window` VARCHAR(50) NOT NULL,
                `description` TEXT NOT NULL,
                `badge` VARCHAR(50) NULL,
                `latency_ms` INT DEFAULT 200,
                `is_popular` INT DEFAULT 0
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS `usage_logs` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `user_id` INT NOT NULL,
                `key_id` INT NULL,
                `model_slug` VARCHAR(100) NOT NULL,
                `tokens_prompt` INT DEFAULT 0,
                `tokens_completion` INT DEFAULT 0,
                `cost_rub` DOUBLE NOT NULL,
                `latency_ms` INT DEFAULT 0,
                `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS `promo_codes` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `code` VARCHAR(100) NOT NULL UNIQUE,
                `bonus_amount` DOUBLE NOT NULL,
                `description` TEXT NULL,
                `max_uses` INT DEFAULT 1000,
                `used_count` INT DEFAULT 0,
                `is_active` INT DEFAULT 1
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS `used_promos` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `user_id` INT NOT NULL,
                `promo_code` VARCHAR(100) NOT NULL,
                `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY `user_promo_unique` (`user_id`, `promo_code`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            conn.commit()

            # Seed models in MySQL
            cur.execute("SELECT COUNT(*) as cnt FROM `models`")
            row = cur.fetchone()
            if row and row['cnt'] == 0:
                _seed_models_mysql(cur, conn)

            # Seed promo codes in MySQL
            cur.execute("SELECT COUNT(*) as cnt FROM `promo_codes`")
            row = cur.fetchone()
            if row and row['cnt'] == 0:
                _seed_promos_mysql(cur, conn)

            cur.close()
            conn.close()
            print("MySQL database initialized successfully!")
            return
        except Exception as e:
            print("MySQL init error:", e)
            if conn: conn.close()

    # SQLite initialization
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        balance REAL NOT NULL DEFAULT 150.0,
        total_spent REAL NOT NULL DEFAULT 0.0,
        total_deposited REAL NOT NULL DEFAULT 0.0,
        tier TEXT DEFAULT 'Developer',
        avatar_color TEXT DEFAULT '#6366f1',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        key_hash TEXT NOT NULL,
        key_prefix TEXT NOT NULL,
        spend_limit REAL DEFAULT 0.0,
        spent REAL DEFAULT 0.0,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used_at TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        type TEXT NOT NULL,
        payment_method TEXT,
        description TEXT NOT NULL,
        status TEXT DEFAULT 'success',
        reference_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS models (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        provider TEXT NOT NULL,
        category TEXT NOT NULL,
        price_input_1m REAL NOT NULL,
        price_output_1m REAL NOT NULL,
        context_window TEXT NOT NULL,
        description TEXT NOT NULL,
        badge TEXT,
        latency_ms INTEGER DEFAULT 200,
        is_popular INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS usage_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        key_id INTEGER,
        model_slug TEXT NOT NULL,
        tokens_prompt INTEGER DEFAULT 0,
        tokens_completion INTEGER DEFAULT 0,
        cost_rub REAL NOT NULL,
        latency_ms INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS promo_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        bonus_amount REAL NOT NULL,
        description TEXT,
        max_uses INTEGER DEFAULT 1000,
        used_count INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS used_promos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        promo_code TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        UNIQUE(user_id, promo_code)
    )
    """)

    conn.commit()

    cur.execute("SELECT COUNT(*) as cnt FROM models")
    if cur.fetchone()["cnt"] == 0:
        _seed_models_sqlite(cur, conn)

    cur.execute("SELECT COUNT(*) as cnt FROM promo_codes")
    if cur.fetchone()["cnt"] == 0:
        _seed_promos_sqlite(cur, conn)

    # Demo user
    cur.execute("SELECT COUNT(*) as cnt FROM users")
    if cur.fetchone()["cnt"] == 0:
        demo_pass_hash = hash_password("demo123")
        cur.execute("""
        INSERT INTO users (username, email, password_hash, balance, total_spent, total_deposited, tier, avatar_color)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, ("Александр Смирнов", "demo@neuroapi.io", demo_pass_hash, 1250.0, 340.5, 1500.0, "Pro Developer", "#6366f1"))
        demo_user_id = cur.lastrowid

        demo_key_raw = generate_api_key()
        demo_key_hash = hash_password(demo_key_raw)
        demo_key_prefix = demo_key_raw[:14] + "..." + demo_key_raw[-4:]
        cur.execute("""
        INSERT INTO api_keys (user_id, name, key_hash, key_prefix, spend_limit, spent, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (demo_user_id, "Основной API ключ (Production)", demo_key_hash, demo_key_prefix, 5000.0, 340.5, 1))

        conn.commit()

    conn.close()

def _get_seed_models_data():
    return [
        ("gpt-4o", "GPT-4o Omni", "OpenAI", "text", 225.0, 900.0, "128k", "Флагманская мультимодальная модель от OpenAI: высокая скорость и глубокое понимание контекста", "ХИТ", 180, 1),
        ("gpt-4o-mini", "GPT-4o Mini", "OpenAI", "text", 13.5, 54.0, "128k", "Ультрабыстрая и экономичная модель для базовых задач и чат-ботов", "ЭКОНОМ", 110, 1),
        ("o1-preview", "o1 Reasoning", "OpenAI", "reasoning", 1350.0, 5400.0, "128k", "Модель глубоких рассуждений для сложных научных, математических и архитектурных задач", "PRO", 750, 0),
        ("o3-mini", "o3-mini STEM", "OpenAI", "reasoning", 99.0, 396.0, "200k", "Компактная reasoning модель нового поколения для точного программирования и логики", "NEW", 280, 1),
        ("claude-3-5-sonnet", "Claude 3.5 Sonnet", "Anthropic", "text", 270.0, 1350.0, "200k", "Лучшая в мире модель для написания сложного кода, анализа архитектуры и аналитики", "ТОП КОД", 210, 1),
        ("claude-3-5-haiku", "Claude 3.5 Haiku", "Anthropic", "text", 72.0, 360.0, "200k", "Молниеносная модель с высоким интеллектом для реального времени и суппорта", "БЫСТРЫЙ", 95, 1),
        ("deepseek-chat-v3", "DeepSeek V3 (671B)", "DeepSeek", "text", 12.0, 24.0, "64k", "Мощная открытая модель мирового уровня с рекордно низкой стоимостью токенов", "ВЫГОДА", 150, 1),
        ("deepseek-reasoner-r1", "DeepSeek R1", "DeepSeek", "reasoning", 49.0, 195.0, "64k", "Продвинутая модель логического вывода и рассуждений (CoT), соперник o1", "ТРЕНД", 420, 1),
        ("llama-3.3-70b", "Llama 3.3 70B Instruct", "Meta", "text", 28.0, 72.0, "128k", "Мощнейшая открытая модель Meta с качеством на уровне GPT-4", "OPEN", 140, 0),
        ("qwen-2.5-coder-32b", "Qwen 2.5 Coder 32B", "Alibaba", "code", 18.0, 54.0, "128k", "Специализированная нейросеть для генерации, рефакторинга и поиска багов в коде", "КОДИНГ", 130, 0),
        ("mistral-large-2411", "Mistral Large 2", "Mistral AI", "text", 180.0, 540.0, "128k", "Европейская флагманская языковая модель с отличным русским и логикой", "PRO", 190, 0),
        ("flux-1-schnell", "FLUX.1 Schnell", "Black Forest Labs", "image", 2.5, 2.5, "1k x 1k", "Генерация фотореалистичных изображений за 1-2 секунды (цена за 1 генерацию)", "БЫСТРЫЙ", 1200, 1),
        ("flux-1-dev", "FLUX.1 Dev HQ", "Black Forest Labs", "image", 4.9, 4.9, "2k x 2k", "Максимальная детализация, точное следование тексту и анатомии (за генерацию)", "HQ", 3500, 1),
        ("midjourney-v6-api", "Midjourney v6.1 API", "Midjourney", "image", 6.5, 6.5, "HD/UHD", "Художественные шедевры, брендинг, концепт-арт через прямой API (за генерацию)", "АРТ", 4500, 1),
        ("dall-e-3", "DALL-E 3 HD", "OpenAI", "image", 3.8, 3.8, "1024x1024", "Генерация сложных сцен с точным пониманием длинных промптов (за генерацию)", "OPENAI", 2800, 0),
        ("whisper-large-v3", "Whisper Large v3", "OpenAI", "audio", 0.45, 0.45, "Аудио", "Сверхточное распознавание речи на 99 языках с таймкодами (цена за 1 минуту)", "АУДИО", 450, 0),
        ("elevenlabs-v2", "ElevenLabs Turbo v2", "ElevenLabs", "audio", 1.80, 1.80, "1k симв.", "Естественная озвучка текста эмоциональными человеческими голосами (за 1k симв.)", "ГОЛОС", 600, 0)
    ]

def _seed_models_sqlite(cur, conn):
    cur.executemany("""
    INSERT INTO models (slug, name, provider, category, price_input_1m, price_output_1m, context_window, description, badge, latency_ms, is_popular)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, _get_seed_models_data())
    conn.commit()

def _seed_models_mysql(cur, conn):
    cur.executemany("""
    INSERT INTO `models` (`slug`, `name`, `provider`, `category`, `price_input_1m`, `price_output_1m`, `context_window`, `description`, `badge`, `latency_ms`, `is_popular`)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, _get_seed_models_data())
    conn.commit()

def _seed_promos_sqlite(cur, conn):
    promos = [
        ("NEURO2026", 500.0, "Промокод на 500 ₽ для новых разработчиков"),
        ("WELCOME100", 100.0, "Приветственный бонус 100 ₽"),
        ("DEV500", 500.0, "Бонус для разработчиков +500 ₽"),
        ("DUCKAI", 250.0, "Бонус от сообщества +250 ₽"),
        ("STARTAI", 300.0, "Быстрый старт +300 ₽")
    ]
    cur.executemany("INSERT INTO promo_codes (code, bonus_amount, description) VALUES (?, ?, ?)", promos)
    conn.commit()

def _seed_promos_mysql(cur, conn):
    promos = [
        ("NEURO2026", 500.0, "Промокод на 500 ₽ для новых разработчиков"),
        ("WELCOME100", 100.0, "Приветственный бонус 100 ₽"),
        ("DEV500", 500.0, "Бонус для разработчиков +500 ₽"),
        ("DUCKAI", 250.0, "Бонус от сообщества +250 ₽"),
        ("STARTAI", 300.0, "Быстрый старт +300 ₽")
    ]
    cur.executemany("INSERT INTO `promo_codes` (`code`, `bonus_amount`, `description`) VALUES (%s, %s, %s)", promos)
    conn.commit()

# -------------------------------------------------------------
# USER CRUD OPERATIONS
# -------------------------------------------------------------

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    db_type, conn = get_db()
    clean_email = email.strip().lower()
    
    if db_type == "mysql":
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM `users` WHERE `email` = %s", (clean_email,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            if 'balance' not in row or row['balance'] is None: row['balance'] = 150.0
            if 'total_spent' not in row or row['total_spent'] is None: row['total_spent'] = 0.0
            if 'total_deposited' not in row or row['total_deposited'] is None: row['total_deposited'] = 0.0
        return row
    else:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = ?", (clean_email,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    db_type, conn = get_db()
    
    if db_type == "mysql":
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM `users` WHERE `id` = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            if 'balance' not in row or row['balance'] is None: row['balance'] = 150.0
            if 'total_spent' not in row or row['total_spent'] is None: row['total_spent'] = 0.0
            if 'total_deposited' not in row or row['total_deposited'] is None: row['total_deposited'] = 0.0
        return row
    else:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

def create_user(username: str, email: str, password_hash: str, initial_bonus: float = 150.0) -> Dict[str, Any]:
    colors = ["#6366f1", "#8b5cf6", "#ec4899", "#3b82f6", "#10b981", "#f59e0b", "#06b6d4"]
    avatar_color = secrets.choice(colors)
    clean_name = username.strip()
    clean_email = email.strip().lower()

    db_type, conn = get_db()
    
    if db_type == "mysql":
        cur = conn.cursor(dictionary=True)
        
        # Check if users table has balance column
        cur.execute("DESCRIBE `users`")
        cols = [r['Field'] for r in cur.fetchall()]
        
        if 'balance' in cols:
            cur.execute("""
            INSERT INTO `users` (`username`, `email`, `password_hash`, `balance`, `total_spent`, `total_deposited`, `tier`, `avatar_color`)
            VALUES (%s, %s, %s, %s, 0.0, 0.0, 'Developer', %s)
            """, (clean_name, clean_email, password_hash, initial_bonus, avatar_color))
        else:
            cur.execute("""
            INSERT INTO `users` (`username`, `email`, `password_hash`)
            VALUES (%s, %s, %s)
            """, (clean_name, clean_email, password_hash))
            
        user_id = cur.lastrowid

        # Insert bonus transaction
        try:
            cur.execute("""
            INSERT INTO `transactions` (`user_id`, `amount`, `type`, `payment_method`, `description`, `status`, `reference_id`)
            VALUES (%s, %s, 'bonus', 'system', '🎁 Приветственный бонус на баланс при регистрации', 'success', %s)
            """, (user_id, initial_bonus, f"BONUS-{secrets.token_hex(4).upper()}"))
        except Exception:
            pass

        # Generate default API key
        raw_key = generate_api_key()
        key_hash = hash_password(raw_key)
        key_prefix = raw_key[:14] + "..." + raw_key[-4:]
        try:
            cur.execute("""
            INSERT INTO `api_keys` (`user_id`, `name`, `key_hash`, `key_prefix`, `spend_limit`, `spent`, `is_active`)
            VALUES (%s, %s, %s, %s, 0.0, 0.0, 1)
            """, (user_id, "Основной ключ (Default)", key_hash, key_prefix))
        except Exception:
            pass

        conn.commit()
        cur.execute("SELECT * FROM `users` WHERE `id` = %s", (user_id,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user:
            if 'balance' not in user or user['balance'] is None: user['balance'] = initial_bonus
            if 'total_spent' not in user or user['total_spent'] is None: user['total_spent'] = 0.0
            if 'total_deposited' not in user or user['total_deposited'] is None: user['total_deposited'] = 0.0
            user["initial_key"] = raw_key
            return user
        return {"id": user_id, "username": clean_name, "email": clean_email, "balance": initial_bonus, "initial_key": raw_key}

    else:
        # SQLite
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO users (username, email, password_hash, balance, total_spent, total_deposited, tier, avatar_color)
        VALUES (?, ?, ?, ?, 0.0, 0.0, 'Developer', ?)
        """, (clean_name, clean_email, password_hash, initial_bonus, avatar_color))
        
        user_id = cur.lastrowid
        
        cur.execute("""
        INSERT INTO transactions (user_id, amount, type, payment_method, description, status, reference_id)
        VALUES (?, ?, 'bonus', 'system', '🎁 Приветственный бонус на баланс при регистрации', 'success', ?)
        """, (user_id, initial_bonus, f"BONUS-{secrets.token_hex(4).upper()}"))

        raw_key = generate_api_key()
        key_hash = hash_password(raw_key)
        key_prefix = raw_key[:14] + "..." + raw_key[-4:]
        cur.execute("""
        INSERT INTO api_keys (user_id, name, key_hash, key_prefix, spend_limit, spent, is_active)
        VALUES (?, ?, ?, ?, 0.0, 0.0, 1)
        """, (user_id, "Основной ключ (Default)", key_hash, key_prefix))

        conn.commit()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = dict(cur.fetchone())
        conn.close()
        user["initial_key"] = raw_key
        return user

def add_user_balance(user_id: int, amount: float, method: str = "sbp", description: str = None) -> Dict[str, Any]:
    if amount <= 0:
        raise ValueError("Сумма пополнения должна быть больше 0")

    bonus_pct = 0.0
    if amount >= 10000: bonus_pct = 0.15
    elif amount >= 5000: bonus_pct = 0.10
    elif amount >= 2500: bonus_pct = 0.05
        
    bonus_rub = round(amount * bonus_pct, 2)
    total_credit = round(amount + bonus_rub, 2)
    tx_ref = f"TX-{method.upper()}-{secrets.token_hex(4).upper()}"
    
    if not description:
        desc_parts = [f"Пополнение баланса ({method.upper()}) на {amount:.2f} ₽"]
        if bonus_rub > 0:
            desc_parts.append(f"включая бонус {int(bonus_pct*100)}% (+{bonus_rub:.2f} ₽)")
        description = " ".join(desc_parts)

    db_type, conn = get_db()
    if db_type == "mysql":
        cur = conn.cursor(dictionary=True)
        cur.execute("UPDATE `users` SET `balance` = `balance` + %s, `total_deposited` = `total_deposited` + %s WHERE `id` = %s", (total_credit, amount, user_id))
        cur.execute("""
        INSERT INTO `transactions` (`user_id`, `amount`, `type`, `payment_method`, `description`, `status`, `reference_id`)
        VALUES (%s, %s, 'topup', %s, %s, 'success', %s)
        """, (user_id, total_credit, method, description, tx_ref))
        conn.commit()
        cur.execute("SELECT `balance`, `total_deposited` FROM `users` WHERE `id` = %s", (user_id,))
        user_row = cur.fetchone()
        cur.close()
        conn.close()
        new_balance = user_row["balance"] if user_row else total_credit
    else:
        cur = conn.cursor()
        cur.execute("UPDATE users SET balance = balance + ?, total_deposited = total_deposited + ? WHERE id = ?", (total_credit, amount, user_id))
        cur.execute("""
        INSERT INTO transactions (user_id, amount, type, payment_method, description, status, reference_id)
        VALUES (?, ?, 'topup', ?, ?, 'success', ?)
        """, (user_id, total_credit, method, description, tx_ref))
        conn.commit()
        cur.execute("SELECT balance, total_deposited FROM users WHERE id = ?", (user_id,))
        user_row = dict(cur.fetchone())
        conn.close()
        new_balance = user_row["balance"]

    return {
        "success": True,
        "credited": total_credit,
        "amount": amount,
        "bonus": bonus_rub,
        "new_balance": new_balance,
        "reference_id": tx_ref,
        "description": description
    }

def apply_promo_code(user_id: int, code_str: str) -> Dict[str, Any]:
    code_clean = code_str.strip().upper()
    db_type, conn = get_db()
    
    if db_type == "mysql":
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM `promo_codes` WHERE `code` = %s AND `is_active` = 1", (code_clean,))
        promo = cur.fetchone()
        if not promo:
            cur.close(); conn.close()
            return {"success": False, "error": "Промокод не найден или срок действия истек"}
        
        cur.execute("SELECT `id` FROM `used_promos` WHERE `user_id` = %s AND `promo_code` = %s", (user_id, code_clean))
        if cur.fetchone():
            cur.close(); conn.close()
            return {"success": False, "error": "Вы уже активировали этот промокод"}

        bonus = promo["bonus_amount"]
        cur.execute("UPDATE `users` SET `balance` = `balance` + %s WHERE `id` = %s", (bonus, user_id))
        cur.execute("UPDATE `promo_codes` SET `used_count` = `used_count` + 1 WHERE `id` = %s", (promo["id"],))
        cur.execute("INSERT INTO `used_promos` (`user_id`, `promo_code`) VALUES (%s, %s)", (user_id, code_clean))
        
        tx_ref = f"PROMO-{secrets.token_hex(4).upper()}"
        cur.execute("""
        INSERT INTO `transactions` (`user_id`, `amount`, `type`, `payment_method`, `description`, `status`, `reference_id`)
        VALUES (%s, %s, 'bonus', 'promo', %s, 'success', %s)
        """, (user_id, bonus, f"Активация промокода {code_clean} (+{bonus:.2f} ₽)", tx_ref))
        conn.commit()
        
        cur.execute("SELECT `balance` FROM `users` WHERE `id` = %s", (user_id,))
        new_bal = cur.fetchone()["balance"]
        cur.close(); conn.close()
        
    else:
        cur = conn.cursor()
        cur.execute("SELECT * FROM promo_codes WHERE code = ? AND is_active = 1", (code_clean,))
        promo = cur.fetchone()
        if not promo:
            conn.close()
            return {"success": False, "error": "Промокод не найден или срок действия истек"}
        
        cur.execute("SELECT id FROM used_promos WHERE user_id = ? AND promo_code = ?", (user_id, code_clean))
        if cur.fetchone():
            conn.close()
            return {"success": False, "error": "Вы уже активировали этот промокод"}

        bonus = promo["bonus_amount"]
        cur.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (bonus, user_id))
        cur.execute("UPDATE promo_codes SET used_count = used_count + 1 WHERE id = ?", (promo["id"],))
        cur.execute("INSERT INTO used_promos (user_id, promo_code) VALUES (?, ?)", (user_id, code_clean))
        
        tx_ref = f"PROMO-{secrets.token_hex(4).upper()}"
        cur.execute("""
        INSERT INTO transactions (user_id, amount, type, payment_method, description, status, reference_id)
        VALUES (?, ?, 'bonus', 'promo', ?, 'success', ?)
        """, (user_id, bonus, f"Активация промокода {code_clean} (+{bonus:.2f} ₽)", tx_ref))
        conn.commit()
        
        cur.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
        new_bal = cur.fetchone()["balance"]
        conn.close()

    return {
        "success": True,
        "bonus_amount": bonus,
        "new_balance": new_bal,
        "message": f"Промокод успешно активирован! Начислено {bonus:.2f} ₽"
    }

def debit_user_balance_for_api(user_id: int, cost: float, model_slug: str, prompt_tokens: int, comp_tokens: int, latency_ms: int = 150) -> bool:
    db_type, conn = get_db()
    
    if db_type == "mysql":
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT `balance`, `total_spent` FROM `users` WHERE `id` = %s", (user_id,))
        user = cur.fetchone()
        if not user or (user.get("balance") or 0) < cost:
            cur.close(); conn.close()
            return False
            
        cur.execute("UPDATE `users` SET `balance` = `balance` - %s, `total_spent` = `total_spent` + %s WHERE `id` = %s", (cost, cost, user_id))
        cur.execute("""
        INSERT INTO `usage_logs` (`user_id`, `model_slug`, `tokens_prompt`, `tokens_completion`, `cost_rub`, `latency_ms`)
        VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, model_slug, prompt_tokens, comp_tokens, cost, latency_ms))
        cur.execute("""
        INSERT INTO `transactions` (`user_id`, `amount`, `type`, `payment_method`, `description`, `status`, `reference_id`)
        VALUES (%s, %s, 'usage', 'api_usage', %s, 'success', %s)
        """, (user_id, -cost, f"API запрос к {model_slug} ({prompt_tokens + comp_tokens} токенов)", f"USG-{secrets.token_hex(4).upper()}"))
        conn.commit()
        cur.close(); conn.close()
        return True
    else:
        cur = conn.cursor()
        cur.execute("SELECT balance, total_spent FROM users WHERE id = ?", (user_id,))
        user = cur.fetchone()
        if not user or user["balance"] < cost:
            conn.close()
            return False
            
        cur.execute("UPDATE users SET balance = balance - ?, total_spent = total_spent + ? WHERE id = ?", (cost, cost, user_id))
        cur.execute("""
        INSERT INTO usage_logs (user_id, model_slug, tokens_prompt, tokens_completion, cost_rub, latency_ms)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, model_slug, prompt_tokens, comp_tokens, cost, latency_ms))
        cur.execute("""
        INSERT INTO transactions (user_id, amount, type, payment_method, description, status, reference_id)
        VALUES (?, ?, 'usage', 'api_usage', ?, 'success', ?)
        """, (user_id, -cost, f"API запрос к {model_slug} ({prompt_tokens + comp_tokens} токенов)", f"USG-{secrets.token_hex(4).upper()}"))
        conn.commit()
        conn.close()
        return True

def get_user_transactions(user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    db_type, conn = get_db()
    if db_type == "mysql":
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM `transactions` WHERE `user_id` = %s ORDER BY `created_at` DESC, `id` DESC LIMIT %s", (user_id, limit))
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [dict(r) for r in rows]
    else:
        cur = conn.cursor()
        cur.execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?", (user_id, limit))
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]

def get_user_api_keys(user_id: int) -> List[Dict[str, Any]]:
    db_type, conn = get_db()
    if db_type == "mysql":
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT `id`, `user_id`, `name`, `key_prefix`, `spend_limit`, `spent`, `is_active`, `created_at`, `last_used_at` FROM `api_keys` WHERE `user_id` = %s ORDER BY `created_at` DESC", (user_id,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [dict(r) for r in rows]
    else:
        cur = conn.cursor()
        cur.execute("SELECT id, user_id, name, key_prefix, spend_limit, spent, is_active, created_at, last_used_at FROM api_keys WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]

def create_user_api_key(user_id: int, name: str, spend_limit: float = 0.0) -> Dict[str, Any]:
    raw_key = generate_api_key()
    key_hash = hash_password(raw_key)
    key_prefix = raw_key[:14] + "..." + raw_key[-4:]
    key_name = name.strip() or "API Ключ"
    
    db_type, conn = get_db()
    if db_type == "mysql":
        cur = conn.cursor(dictionary=True)
        cur.execute("""
        INSERT INTO `api_keys` (`user_id`, `name`, `key_hash`, `key_prefix`, `spend_limit`, `spent`, `is_active`)
        VALUES (%s, %s, %s, %s, %s, 0.0, 1)
        """, (user_id, key_name, key_hash, key_prefix, spend_limit))
        key_id = cur.lastrowid
        conn.commit()
        cur.close(); conn.close()
    else:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO api_keys (user_id, name, key_hash, key_prefix, spend_limit, spent, is_active)
        VALUES (?, ?, ?, ?, ?, 0.0, 1)
        """, (user_id, key_name, key_hash, key_prefix, spend_limit))
        key_id = cur.lastrowid
        conn.commit()
        conn.close()
    
    return {
        "id": key_id,
        "name": key_name,
        "raw_key": raw_key,
        "key_prefix": key_prefix,
        "spend_limit": spend_limit,
        "is_active": 1
    }

def delete_user_api_key(user_id: int, key_id: int) -> bool:
    db_type, conn = get_db()
    if db_type == "mysql":
        cur = conn.cursor()
        cur.execute("DELETE FROM `api_keys` WHERE `id` = %s AND `user_id` = %s", (key_id, user_id))
        affected = cur.rowcount
        conn.commit()
        cur.close(); conn.close()
        return affected > 0
    else:
        cur = conn.cursor()
        cur.execute("DELETE FROM api_keys WHERE id = ? AND user_id = ?", (key_id, user_id))
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected > 0

def get_all_models() -> List[Dict[str, Any]]:
    db_type, conn = get_db()
    if db_type == "mysql":
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM `models` ORDER BY `is_popular` DESC, `price_input_1m` ASC")
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [dict(r) for r in rows]
    else:
        cur = conn.cursor()
        cur.execute("SELECT * FROM models ORDER BY is_popular DESC, price_input_1m ASC")
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]

def get_model_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    db_type, conn = get_db()
    if db_type == "mysql":
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM `models` WHERE `slug` = %s", (slug,))
        row = cur.fetchone()
        cur.close(); conn.close()
        return dict(row) if row else None
    else:
        cur = conn.cursor()
        cur.execute("SELECT * FROM models WHERE slug = ?", (slug,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

def get_user_stats(user_id: int) -> Dict[str, Any]:
    db_type, conn = get_db()
    if db_type == "mysql":
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT `balance`, `total_spent`, `total_deposited`, `username`, `email`, `tier`, `avatar_color`, `created_at` FROM `users` WHERE `id` = %s", (user_id,))
        user = cur.fetchone()
        if not user:
            cur.close(); conn.close()
            return {}
        cur.execute("SELECT COUNT(*) as keys_count FROM `api_keys` WHERE `user_id` = %s AND `is_active` = 1", (user_id,))
        keys_count = cur.fetchone()["keys_count"]
        cur.execute("SELECT COUNT(*) as req_count, COALESCE(SUM(`tokens_prompt` + `tokens_completion`), 0) as total_tokens FROM `usage_logs` WHERE `user_id` = %s", (user_id,))
        usage_info = cur.fetchone()
        cur.close(); conn.close()
        if 'balance' not in user or user['balance'] is None: user['balance'] = 150.0
        if 'total_spent' not in user or user['total_spent'] is None: user['total_spent'] = 0.0
        if 'total_deposited' not in user or user['total_deposited'] is None: user['total_deposited'] = 0.0
        return {
            **dict(user),
            "keys_count": keys_count,
            "requests_count": usage_info["req_count"] if usage_info else 0,
            "total_tokens": usage_info["total_tokens"] if usage_info else 0
        }
    else:
        cur = conn.cursor()
        cur.execute("SELECT balance, total_spent, total_deposited, username, email, tier, avatar_color, created_at FROM users WHERE id = ?", (user_id,))
        user = cur.fetchone()
        if not user:
            conn.close()
            return {}
        cur.execute("SELECT COUNT(*) as keys_count FROM api_keys WHERE user_id = ? AND is_active = 1", (user_id,))
        keys_count = cur.fetchone()["keys_count"]
        cur.execute("SELECT COUNT(*) as req_count, COALESCE(SUM(tokens_prompt + tokens_completion), 0) as total_tokens FROM usage_logs WHERE user_id = ?", (user_id,))
        usage_info = cur.fetchone()
        conn.close()
        return {
            **dict(user),
            "keys_count": keys_count,
            "requests_count": usage_info["req_count"] if usage_info else 0,
            "total_tokens": usage_info["total_tokens"] if usage_info else 0
        }
