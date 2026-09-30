import os
import time
import hashlib
import secrets
import sqlite3
import traceback
from typing import Optional, Dict, Any, List

# Original MySQL Database Configuration
DB_CONFIG = {
    "host": "185.114.247.43",
    "port": 3306,
    "database": "sch688_vvedenie",
    "user": "sch688_vvedenie",
    "password": "Qwerty123",
    "connection_timeout": 2,
    "autocommit": True
}

SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "neuroapi.db")

_mysql_last_attempt = 0
_mysql_is_available = None
_COOLDOWN_SECONDS = 30  # Don't hang requests if remote server is unreachable

def get_mysql_connection():
    global _mysql_last_attempt, _mysql_is_available
    
    # If MySQL recently failed, skip retry for COOLDOWN_SECONDS to keep site lightning fast
    now = time.time()
    if _mysql_is_available is False and (now - _mysql_last_attempt) < _COOLDOWN_SECONDS:
        return None

    try:
        import mysql.connector
        _mysql_last_attempt = now
        cnx = mysql.connector.connect(**DB_CONFIG)
        if cnx.is_connected():
            _mysql_is_available = True
            return cnx
    except ImportError:
        _mysql_is_available = False
        print("[DB INFO] mysql-connector-python не установлен. Используется SQLite.")
        return None
    except Exception as e:
        _mysql_is_available = False
        print(f"[DB INFO] Сервер MySQL {DB_CONFIG['host']} недоступен с текущего компьютера ({e}). Используется локальная база.")
        return None
    return None

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def generate_api_key() -> str:
    return f"sk-neuro-{secrets.token_hex(20)}"

def init_db():
    print(f"[DB] Проверка подключения к базе данных...")
    cnx = get_mysql_connection()
    if cnx:
        print(f"[DB SUCCESS] Подключено к оригинальной MySQL базе данных `{DB_CONFIG['database']}` на сервере {DB_CONFIG['host']}!")
        try:
            cur = cnx.cursor(dictionary=True)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `users` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `username` VARCHAR(255) NOT NULL,
                `email` VARCHAR(255) NOT NULL UNIQUE,
                `password_hash` VARCHAR(255) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            cur.execute("DESCRIBE `users`")
            existing_cols = [row['Field'] for row in cur.fetchall()]
            for col, col_type in [('balance', 'DOUBLE DEFAULT 150.0'), ('total_spent', 'DOUBLE DEFAULT 0.0'), ('total_deposited', 'DOUBLE DEFAULT 0.0')]:
                if col not in existing_cols:
                    try: cur.execute(f"ALTER TABLE `users` ADD COLUMN `{col}` {col_type}")
                    except Exception: pass

            cur.execute("""
            CREATE TABLE IF NOT EXISTS `user_balances` (
                `user_id` INT PRIMARY KEY,
                `email` VARCHAR(255) NOT NULL,
                `balance` DOUBLE NOT NULL DEFAULT 150.0,
                `total_spent` DOUBLE NOT NULL DEFAULT 0.0,
                `total_deposited` DOUBLE NOT NULL DEFAULT 0.0
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

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
                `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            cur.close()
            cnx.close()
        except Exception as e:
            if cnx: cnx.close()
    
    # Always ensure SQLite is also initialized as reliable fallback
    _init_sqlite()

def _init_sqlite():
    os.makedirs(os.path.dirname(SQLITE_PATH), exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("PRAGMA journal_mode = WAL")
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Seed demo user in SQLite if empty
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        demo_hash = hash_password("demo123")
        cur.execute("""
        INSERT INTO users (username, email, password_hash, balance, total_spent, total_deposited, tier)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("Александр Смирнов", "demo@neuroapi.io", demo_hash, 1250.0, 340.5, 1500.0, "Pro Developer"))
        demo_id = cur.lastrowid
        cur.execute("""
        INSERT INTO api_keys (user_id, name, key_hash, key_prefix, spend_limit, spent, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (demo_id, "Основной API ключ (Production)", hash_password(generate_api_key()), "sk-neuro-demo...84a2", 5000.0, 340.5, 1))

    conn.commit()
    conn.close()

# -------------------------------------------------------------
# USER AUTH OPERATIONS
# -------------------------------------------------------------

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    clean_email = email.strip().lower()
    cnx = get_mysql_connection()
    if cnx:
        try:
            cur = cnx.cursor(dictionary=True)
            cur.execute("SELECT * FROM `users` WHERE `email` = %s", (clean_email,))
            user = cur.fetchone()
            if user:
                user_id = user['id']
                try:
                    cur.execute("SELECT `balance`, `total_spent`, `total_deposited` FROM `user_balances` WHERE `user_id` = %s", (user_id,))
                    bal_row = cur.fetchone()
                    if bal_row:
                        user['balance'] = bal_row['balance']
                        user['total_spent'] = bal_row['total_spent']
                        user['total_deposited'] = bal_row['total_deposited']
                    else:
                        user['balance'] = user.get('balance', 150.0) or 150.0
                        user['total_spent'] = user.get('total_spent', 0.0) or 0.0
                        user['total_deposited'] = user.get('total_deposited', 0.0) or 0.0
                except Exception:
                    user['balance'] = user.get('balance', 150.0) or 150.0
                    user['total_spent'] = user.get('total_spent', 0.0) or 0.0
                    user['total_deposited'] = user.get('total_deposited', 0.0) or 0.0
            cur.close()
            cnx.close()
            if user:
                return user
        except Exception:
            if cnx: cnx.close()

    # SQLite fallback
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (clean_email,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    cnx = get_mysql_connection()
    if cnx:
        try:
            cur = cnx.cursor(dictionary=True)
            cur.execute("SELECT * FROM `users` WHERE `id` = %s", (user_id,))
            user = cur.fetchone()
            if user:
                try:
                    cur.execute("SELECT `balance`, `total_spent`, `total_deposited` FROM `user_balances` WHERE `user_id` = %s", (user_id,))
                    bal_row = cur.fetchone()
                    if bal_row:
                        user['balance'] = bal_row['balance']
                        user['total_spent'] = bal_row['total_spent']
                        user['total_deposited'] = bal_row['total_deposited']
                    else:
                        user['balance'] = user.get('balance', 150.0) or 150.0
                        user['total_spent'] = user.get('total_spent', 0.0) or 0.0
                        user['total_deposited'] = user.get('total_deposited', 0.0) or 0.0
                except Exception:
                    user['balance'] = user.get('balance', 150.0) or 150.0
                    user['total_spent'] = user.get('total_spent', 0.0) or 0.0
                    user['total_deposited'] = user.get('total_deposited', 0.0) or 0.0
            cur.close()
            cnx.close()
            if user:
                return user
        except Exception:
            if cnx: cnx.close()

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def create_user(username: str, email: str, password_hash: str, initial_bonus: float = 150.0) -> Dict[str, Any]:
    clean_name = username.strip()
    clean_email = email.strip().lower()

    cnx = get_mysql_connection()
    if cnx:
        try:
            print(f"[MySQL] Регистрация: INSERT INTO `users`(`username`, `email`, `password_hash`) VALUES ('{clean_name}', '{clean_email}', '***')")
            cur = cnx.cursor(dictionary=True)
            query = 'INSERT INTO `users`(`username`, `email`, `password_hash`) VALUES (%s, %s, %s)'
            cur.execute(query, (clean_name, clean_email, password_hash))
            user_id = cur.lastrowid

            try:
                cur.execute("""
                INSERT INTO `user_balances` (`user_id`, `email`, `balance`, `total_spent`, `total_deposited`)
                VALUES (%s, %s, %s, 0.0, 0.0)
                ON DUPLICATE KEY UPDATE `balance` = %s
                """, (user_id, clean_email, initial_bonus, initial_bonus))
            except Exception:
                pass

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

            cnx.commit()
            cur.close()
            cnx.close()
            print(f"[MySQL SUCCESS] Пользователь {clean_email} успешно зарегистрирован в MySQL базе! ID: {user_id}")
            return {
                "id": user_id,
                "username": clean_name,
                "email": clean_email,
                "balance": initial_bonus,
                "initial_key": raw_key
            }
        except Exception as e:
            if cnx: cnx.close()

    # SQLite
    conn = sqlite3.connect(SQLITE_PATH)
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO users (username, email, password_hash, balance, total_spent, total_deposited)
    VALUES (?, ?, ?, ?, 0.0, 0.0)
    """, (clean_name, clean_email, password_hash, initial_bonus))
    user_id = cur.lastrowid

    raw_key = generate_api_key()
    key_hash = hash_password(raw_key)
    key_prefix = raw_key[:14] + "..." + raw_key[-4:]
    cur.execute("""
    INSERT INTO api_keys (user_id, name, key_hash, key_prefix, spend_limit, spent, is_active)
    VALUES (?, ?, ?, ?, 0.0, 0.0, 1)
    """, (user_id, "Основной ключ (Default)", key_hash, key_prefix))

    conn.commit()
    conn.close()
    return {
        "id": user_id,
        "username": clean_name,
        "email": clean_email,
        "balance": initial_bonus,
        "initial_key": raw_key
    }

# -------------------------------------------------------------
# BALANCE & TRANSACTIONS
# -------------------------------------------------------------

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

    cnx = get_mysql_connection()
    if cnx:
        try:
            cur = cnx.cursor(dictionary=True)
            cur.execute("""
            INSERT INTO `user_balances` (`user_id`, `email`, `balance`, `total_spent`, `total_deposited`)
            VALUES (%s, '', %s, 0.0, %s)
            ON DUPLICATE KEY UPDATE `balance` = `balance` + %s, `total_deposited` = `total_deposited` + %s
            """, (user_id, total_credit, amount, total_credit, amount))

            try: cur.execute("UPDATE `users` SET `balance` = `balance` + %s WHERE `id` = %s", (total_credit, user_id))
            except Exception: pass

            cur.execute("""
            INSERT INTO `transactions` (`user_id`, `amount`, `type`, `payment_method`, `description`, `status`, `reference_id`)
            VALUES (%s, %s, 'topup', %s, %s, 'success', %s)
            """, (user_id, total_credit, method, description, tx_ref))

            cnx.commit()
            cur.execute("SELECT `balance` FROM `user_balances` WHERE `user_id` = %s", (user_id,))
            row = cur.fetchone()
            cur.close()
            cnx.close()
            new_balance = row['balance'] if row else total_credit
            return {
                "success": True,
                "credited": total_credit,
                "amount": amount,
                "bonus": bonus_rub,
                "new_balance": new_balance,
                "reference_id": tx_ref,
                "description": description
            }
        except Exception:
            if cnx: cnx.close()

    # SQLite
    conn = sqlite3.connect(SQLITE_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + ?, total_deposited = total_deposited + ? WHERE id = ?", (total_credit, amount, user_id))
    cur.execute("""
    INSERT INTO transactions (user_id, amount, type, payment_method, description, status, reference_id)
    VALUES (?, ?, 'topup', ?, ?, 'success', ?)
    """, (user_id, total_credit, method, description, tx_ref))
    conn.commit()
    cur.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return {
        "success": True,
        "credited": total_credit,
        "amount": amount,
        "bonus": bonus_rub,
        "new_balance": row[0] if row else total_credit,
        "reference_id": tx_ref,
        "description": description
    }

def apply_promo_code(user_id: int, code_str: str) -> Dict[str, Any]:
    code_clean = code_str.strip().upper()
    cnx = get_mysql_connection()
    if cnx:
        try:
            cur = cnx.cursor(dictionary=True)
            cur.execute("SELECT * FROM `promo_codes` WHERE `code` = %s AND `is_active` = 1", (code_clean,))
            promo = cur.fetchone()
            if not promo:
                cur.close(); cnx.close()
                return {"success": False, "error": "Промокод не найден"}

            cur.execute("SELECT `id` FROM `used_promos` WHERE `user_id` = %s AND `promo_code` = %s", (user_id, code_clean))
            if cur.fetchone():
                cur.close(); cnx.close()
                return {"success": False, "error": "Вы уже активировали этот промокод"}

            bonus = promo["bonus_amount"]
            cur.execute("""
            INSERT INTO `user_balances` (`user_id`, `email`, `balance`, `total_spent`, `total_deposited`)
            VALUES (%s, '', %s, 0.0, 0.0)
            ON DUPLICATE KEY UPDATE `balance` = `balance` + %s
            """, (user_id, bonus, bonus))

            cur.execute("INSERT INTO `used_promos` (`user_id`, `promo_code`) VALUES (%s, %s)", (user_id, code_clean))
            cur.execute("""
            INSERT INTO `transactions` (`user_id`, `amount`, `type`, `payment_method`, `description`, `status`, `reference_id`)
            VALUES (%s, %s, 'bonus', 'promo', %s, 'success', %s)
            """, (user_id, bonus, f"Активация промокода {code_clean} (+{bonus:.2f} ₽)", f"PROMO-{secrets.token_hex(4).upper()}"))
            cnx.commit()

            cur.execute("SELECT `balance` FROM `user_balances` WHERE `user_id` = %s", (user_id,))
            new_bal = cur.fetchone()['balance']
            cur.close(); cnx.close()
            return {"success": True, "bonus_amount": bonus, "new_balance": new_bal, "message": f"Промокод активирован! Начислено {bonus:.2f} ₽"}
        except Exception:
            if cnx: cnx.close()

    # SQLite
    conn = sqlite3.connect(SQLITE_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM promo_codes WHERE code = ? AND is_active = 1", (code_clean,))
    promo = cur.fetchone()
    if not promo:
        conn.close()
        return {"success": False, "error": "Промокод не найден"}

    cur.execute("SELECT id FROM used_promos WHERE user_id = ? AND promo_code = ?", (user_id, code_clean))
    if cur.fetchone():
        conn.close()
        return {"success": False, "error": "Вы уже активировали этот промокод"}

    bonus = promo[2]
    cur.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (bonus, user_id))
    cur.execute("INSERT INTO used_promos (user_id, promo_code) VALUES (?, ?)", (user_id, code_clean))
    cur.execute("""
    INSERT INTO transactions (user_id, amount, type, payment_method, description, status, reference_id)
    VALUES (?, ?, 'bonus', 'promo', ?, 'success', ?)
    """, (user_id, bonus, f"Активация промокода {code_clean} (+{bonus:.2f} ₽)", f"PROMO-{secrets.token_hex(4).upper()}"))
    conn.commit()
    cur.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    new_bal = cur.fetchone()[0]
    conn.close()
    return {"success": True, "bonus_amount": bonus, "new_balance": new_bal, "message": f"Промокод активирован! Начислено {bonus:.2f} ₽"}

def debit_user_balance_for_api(user_id: int, cost: float, model_slug: str, prompt_tokens: int, comp_tokens: int, latency_ms: int = 150) -> bool:
    user = get_user_by_id(user_id)
    if not user or (user.get('balance') or 0) < cost:
        return False

    cnx = get_mysql_connection()
    if cnx:
        try:
            cur = cnx.cursor()
            cur.execute("""
            UPDATE `user_balances`
            SET `balance` = `balance` - %s, `total_spent` = `total_spent` + %s
            WHERE `user_id` = %s
            """, (cost, cost, user_id))
            cur.execute("""
            INSERT INTO `transactions` (`user_id`, `amount`, `type`, `payment_method`, `description`, `status`, `reference_id`)
            VALUES (%s, %s, 'usage', 'api_usage', %s, 'success', %s)
            """, (user_id, -cost, f"API запрос: {model_slug} ({prompt_tokens + comp_tokens} токенов)", f"USG-{secrets.token_hex(4).upper()}"))
            cnx.commit()
            cur.close(); cnx.close()
            return True
        except Exception:
            if cnx: cnx.close()

    conn = sqlite3.connect(SQLITE_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance - ?, total_spent = total_spent + ? WHERE id = ?", (cost, cost, user_id))
    cur.execute("""
    INSERT INTO transactions (user_id, amount, type, payment_method, description, status, reference_id)
    VALUES (?, ?, 'usage', 'api_usage', ?, 'success', ?)
    """, (user_id, -cost, f"API запрос: {model_slug} ({prompt_tokens + comp_tokens} токенов)", f"USG-{secrets.token_hex(4).upper()}"))
    conn.commit()
    conn.close()
    return True

def get_user_transactions(user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    cnx = get_mysql_connection()
    if cnx:
        try:
            cur = cnx.cursor(dictionary=True)
            cur.execute("SELECT * FROM `transactions` WHERE `user_id` = %s ORDER BY `created_at` DESC, `id` DESC LIMIT %s", (user_id, limit))
            rows = cur.fetchall()
            cur.close(); cnx.close()
            return rows
        except Exception:
            if cnx: cnx.close()

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?", (user_id, limit))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_user_api_keys(user_id: int) -> List[Dict[str, Any]]:
    cnx = get_mysql_connection()
    if cnx:
        try:
            cur = cnx.cursor(dictionary=True)
            cur.execute("SELECT `id`, `user_id`, `name`, `key_prefix`, `spend_limit`, `spent`, `is_active`, `created_at` FROM `api_keys` WHERE `user_id` = %s ORDER BY `created_at` DESC", (user_id,))
            rows = cur.fetchall()
            cur.close(); cnx.close()
            return rows
        except Exception:
            if cnx: cnx.close()

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, name, key_prefix, spend_limit, spent, is_active, created_at FROM api_keys WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_user_api_key(user_id: int, name: str, spend_limit: float = 0.0) -> Dict[str, Any]:
    raw_key = generate_api_key()
    key_hash = hash_password(raw_key)
    key_prefix = raw_key[:14] + "..." + raw_key[-4:]
    key_name = name.strip() or "API Ключ"

    cnx = get_mysql_connection()
    if cnx:
        try:
            cur = cnx.cursor()
            cur.execute("""
            INSERT INTO `api_keys` (`user_id`, `name`, `key_hash`, `key_prefix`, `spend_limit`, `spent`, `is_active`)
            VALUES (%s, %s, %s, %s, %s, 0.0, 1)
            """, (user_id, key_name, key_hash, key_prefix, spend_limit))
            key_id = cur.lastrowid
            cnx.commit()
            cur.close(); cnx.close()
            return {"id": key_id, "name": key_name, "raw_key": raw_key, "key_prefix": key_prefix, "spend_limit": spend_limit}
        except Exception:
            if cnx: cnx.close()

    conn = sqlite3.connect(SQLITE_PATH)
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO api_keys (user_id, name, key_hash, key_prefix, spend_limit, spent, is_active)
    VALUES (?, ?, ?, ?, ?, 0.0, 1)
    """, (user_id, key_name, key_hash, key_prefix, spend_limit))
    key_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {"id": key_id, "name": key_name, "raw_key": raw_key, "key_prefix": key_prefix, "spend_limit": spend_limit}

def delete_user_api_key(user_id: int, key_id: int) -> bool:
    cnx = get_mysql_connection()
    if cnx:
        try:
            cur = cnx.cursor()
            cur.execute("DELETE FROM `api_keys` WHERE `id` = %s AND `user_id` = %s", (key_id, user_id))
            affected = cur.rowcount
            cnx.commit()
            cur.close(); cnx.close()
            return affected > 0
        except Exception:
            if cnx: cnx.close()

    conn = sqlite3.connect(SQLITE_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM api_keys WHERE id = ? AND user_id = ?", (key_id, user_id))
    affected = cur.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def get_all_models() -> List[Dict[str, Any]]:
    return [
        {"slug": "gpt-4o", "name": "GPT-4o Omni", "provider": "OpenAI", "category": "text", "price_input_1m": 225.0, "price_output_1m": 900.0, "context_window": "128k", "description": "Флагманская мультимодальная модель от OpenAI: высокая скорость и глубокое понимание контекста", "badge": "ХИТ"},
        {"slug": "gpt-4o-mini", "name": "GPT-4o Mini", "provider": "OpenAI", "category": "text", "price_input_1m": 13.5, "price_output_1m": 54.0, "context_window": "128k", "description": "Ультрабыстрая и экономичная модель для базовых задач и чат-ботов", "badge": "ЭКОНОМ"},
        {"slug": "o1-preview", "name": "o1 Reasoning", "provider": "OpenAI", "category": "reasoning", "price_input_1m": 1350.0, "price_output_1m": 5400.0, "context_window": "128k", "description": "Модель глубоких рассуждений для сложных научных, математических и архитектурных задач", "badge": "PRO"},
        {"slug": "o3-mini", "name": "o3-mini STEM", "provider": "OpenAI", "category": "reasoning", "price_input_1m": 99.0, "price_output_1m": 396.0, "context_window": "200k", "description": "Компактная reasoning модель нового поколения для точного программирования и логики", "badge": "NEW"},
        {"slug": "claude-3-5-sonnet", "name": "Claude 3.5 Sonnet", "provider": "Anthropic", "category": "text", "price_input_1m": 270.0, "price_output_1m": 1350.0, "context_window": "200k", "description": "Лучшая в мире модель для написания сложного кода, анализа архитектуры и аналитики", "badge": "ТОП КОД"},
        {"slug": "claude-3-5-haiku", "name": "Claude 3.5 Haiku", "provider": "Anthropic", "category": "text", "price_input_1m": 72.0, "price_output_1m": 360.0, "context_window": "200k", "description": "Молниеносная модель с высоким интеллектом для реального времени и суппорта", "badge": "БЫСТРЫЙ"},
        {"slug": "deepseek-chat-v3", "name": "DeepSeek V3 (671B)", "provider": "DeepSeek", "category": "text", "price_input_1m": 12.0, "price_output_1m": 24.0, "context_window": "64k", "description": "Мощная открытая модель мирового уровня с рекордно низкой стоимостью токенов", "badge": "ВЫГОДА"},
        {"slug": "deepseek-reasoner-r1", "name": "DeepSeek R1", "provider": "DeepSeek", "category": "reasoning", "price_input_1m": 49.0, "price_output_1m": 195.0, "context_window": "64k", "description": "Продвинутая модель логического вывода и рассуждений (CoT), соперник o1", "badge": "ТРЕНД"},
        {"slug": "llama-3.3-70b", "name": "Llama 3.3 70B Instruct", "provider": "Meta", "category": "text", "price_input_1m": 28.0, "price_output_1m": 72.0, "context_window": "128k", "description": "Мощнейшая открытая модель Meta с качеством на уровне GPT-4", "badge": "OPEN"},
        {"slug": "qwen-2.5-coder-32b", "name": "Qwen 2.5 Coder 32B", "provider": "Alibaba", "category": "code", "price_input_1m": 18.0, "price_output_1m": 54.0, "context_window": "128k", "description": "Специализированная нейросеть для генерации, рефакторинга и поиска багов в коде", "badge": "КОДИНГ"},
        {"slug": "flux-1-schnell", "name": "FLUX.1 Schnell", "provider": "Black Forest Labs", "category": "image", "price_input_1m": 2.5, "price_output_1m": 2.5, "context_window": "1k x 1k", "description": "Генерация фотореалистичных изображений за 1-2 секунды (цена за 1 генерацию)", "badge": "БЫСТРЫЙ"},
        {"slug": "flux-1-dev", "name": "FLUX.1 Dev HQ", "provider": "Black Forest Labs", "category": "image", "price_input_1m": 4.9, "price_output_1m": 4.9, "context_window": "2k x 2k", "description": "Максимальная детализация, точное следование тексту и анатомии (за генерацию)", "badge": "HQ"},
        {"slug": "midjourney-v6-api", "name": "Midjourney v6.1 API", "provider": "Midjourney", "category": "image", "price_input_1m": 6.5, "price_output_1m": 6.5, "context_window": "HD/UHD", "description": "Художественные шедевры, брендинг, концепт-арт через прямой API (за генерацию)", "badge": "АРТ"},
        {"slug": "whisper-large-v3", "name": "Whisper Large v3", "provider": "OpenAI", "category": "audio", "price_input_1m": 0.45, "price_output_1m": 0.45, "context_window": "Аудио", "description": "Сверхточное распознавание речи на 99 языках с таймкодами (цена за 1 минуту)", "badge": "АУДИО"}
    ]

def get_model_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    models = get_all_models()
    for m in models:
        if m["slug"] == slug:
            return m
    return models[0] if models else None

def get_user_stats(user_id: int) -> Dict[str, Any]:
    user = get_user_by_id(user_id)
    if not user:
        return {}
    keys = get_user_api_keys(user_id)
    txs = get_user_transactions(user_id)
    return {
        **user,
        "keys_count": len(keys),
        "requests_count": len([t for t in txs if t.get('type') == 'usage']),
        "total_tokens": len([t for t in txs if t.get('type') == 'usage']) * 320
    }
