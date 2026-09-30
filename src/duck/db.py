import os
import hashlib
import secrets
import mysql.connector
from typing import Optional, Dict, Any, List

# Original MySQL Database Configuration — ONLY this database is used!
DB_CONFIG = {
    "host": "185.114.247.43",
    "port": 3306,
    "database": "sch688_vvedenie",
    "user": "sch688_vvedenie",
    "password": "Qwerty123",
    "connection_timeout": 10,
    "autocommit": True
}

# In-memory stores for auxiliary data if MySQL user permissions don't allow CREATE TABLE
_memory_balances = {}  # {user_id: {"balance": float, "total_spent": float, "total_deposited": float}}
_memory_transactions = {}  # {user_id: [tx_dict, ...]}
_memory_keys = {}  # {user_id: [key_dict, ...]}
_memory_used_promos = set()  # {(user_id, promo_code), ...}

def get_connection():
    """Create and return a fresh MySQL connection."""
    return mysql.connector.connect(**DB_CONFIG)

def hash_password(password: str) -> str:
    """SHA-256 password hashing matching original code."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def generate_api_key() -> str:
    return f"sk-neuro-{secrets.token_hex(20)}"

def init_db():
    """Initialize MySQL connection and ensure tables exist without crashing if permissions are restricted."""
    print(f"[MySQL] Подключение к базе данных {DB_CONFIG['database']} на сервере {DB_CONFIG['host']}...")
    cnx = None
    cur = None
    try:
        cnx = get_connection()
        cur = cnx.cursor(buffered=True)

        # 1. Ensure original users table exists
        cur.execute("""
        CREATE TABLE IF NOT EXISTS `users` (
            `id` INT AUTO_INCREMENT PRIMARY KEY,
            `username` VARCHAR(255) NOT NULL,
            `email` VARCHAR(255) NOT NULL UNIQUE,
            `password_hash` VARCHAR(255) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # 2. Try to create auxiliary tables if MySQL permissions allow
        try:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `user_balances` (
                `user_id` INT PRIMARY KEY,
                `balance` DOUBLE NOT NULL DEFAULT 150.0,
                `total_spent` DOUBLE NOT NULL DEFAULT 0.0,
                `total_deposited` DOUBLE NOT NULL DEFAULT 0.0
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
        except Exception as e:
            print(f"[MySQL Notice] Таблица user_balances: {e}")

        try:
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
        except Exception as e:
            print(f"[MySQL Notice] Таблица api_keys: {e}")

        try:
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
        except Exception as e:
            print(f"[MySQL Notice] Таблица transactions: {e}")

        print(f"[MySQL SUCCESS] Успешное подключение к MySQL базе `{DB_CONFIG['database']}`!")
    except mysql.connector.Error as err:
        print(f"[MySQL ERROR] Ошибка подключения к MySQL: {err}")
    finally:
        if cur:
            cur.close()
        if cnx and cnx.is_connected():
            cnx.close()

# -------------------------------------------------------------
# USER AUTH QUERIES (EXACT MYSQL QUERIES)
# -------------------------------------------------------------

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    clean_email = email.strip().lower()
    cnx = None
    cur = None
    try:
        cnx = get_connection()
        cur = cnx.cursor(dictionary=True, buffered=True)
        query = "SELECT * FROM `users` WHERE `email` = %s"
        cur.execute(query, (clean_email,))
        user = cur.fetchone()
        if user:
            user = _enrich_user_data(user, cur)
        return user
    except mysql.connector.Error as err:
        print(f"[MySQL Query Error] get_user_by_email: {err}")
        return None
    finally:
        if cur: cur.close()
        if cnx and cnx.is_connected(): cnx.close()

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    cnx = None
    cur = None
    try:
        cnx = get_connection()
        cur = cnx.cursor(dictionary=True, buffered=True)
        query = "SELECT * FROM `users` WHERE `id` = %s"
        cur.execute(query, (user_id,))
        user = cur.fetchone()
        if user:
            user = _enrich_user_data(user, cur)
        return user
    except mysql.connector.Error as err:
        print(f"[MySQL Query Error] get_user_by_id: {err}")
        return None
    finally:
        if cur: cur.close()
        if cnx and cnx.is_connected(): cnx.close()

def _enrich_user_data(user: dict, cur) -> dict:
    user_id = user['id']
    
    # Try reading balance from MySQL user_balances table
    balance_val = None
    spent_val = 0.0
    dep_val = 0.0

    # 1. If balance column exists directly in users
    if 'balance' in user and user['balance'] is not None:
        balance_val = float(user['balance'])
        spent_val = float(user.get('total_spent', 0.0) or 0.0)
        dep_val = float(user.get('total_deposited', 0.0) or 0.0)
    else:
        # 2. Check user_balances table
        try:
            cur.execute("SELECT `balance`, `total_spent`, `total_deposited` FROM `user_balances` WHERE `user_id` = %s", (user_id,))
            row = cur.fetchone()
            if row:
                balance_val = float(row['balance'])
                spent_val = float(row.get('total_spent', 0.0) or 0.0)
                dep_val = float(row.get('total_deposited', 0.0) or 0.0)
        except Exception:
            pass

    # 3. If not in DB, use in-memory store
    if balance_val is None:
        if user_id in _memory_balances:
            mem = _memory_balances[user_id]
            balance_val = mem['balance']
            spent_val = mem['total_spent']
            dep_val = mem['total_deposited']
        else:
            balance_val = 150.0
            _memory_balances[user_id] = {'balance': 150.0, 'total_spent': 0.0, 'total_deposited': 0.0}

    user['balance'] = balance_val
    user['total_spent'] = spent_val
    user['total_deposited'] = dep_val
    user['tier'] = 'Developer'
    user['avatar_color'] = '#6366f1'
    return user

def create_user(username: str, email: str, password_hash: str, initial_bonus: float = 150.0) -> Dict[str, Any]:
    clean_name = username.strip()
    clean_email = email.strip().lower()

    cnx = None
    cur = None
    try:
        cnx = get_connection()
        cur = cnx.cursor(dictionary=True, buffered=True)

        # EXACT original query
        query = 'INSERT INTO `users`(`username`, `email`, `password_hash`) VALUES (%s, %s, %s)'
        cur.execute(query, (clean_name, clean_email, password_hash))
        cnx.commit()
        user_id = cur.lastrowid

        # Try to save balance in MySQL user_balances table
        try:
            cur.execute("""
            INSERT INTO `user_balances` (`user_id`, `balance`, `total_spent`, `total_deposited`)
            VALUES (%s, %s, 0.0, 0.0)
            ON DUPLICATE KEY UPDATE `balance` = %s
            """, (user_id, initial_bonus, initial_bonus))
            cnx.commit()
        except Exception:
            pass

        # Also store in memory cache
        _memory_balances[user_id] = {
            'balance': initial_bonus,
            'total_spent': 0.0,
            'total_deposited': 0.0
        }

        # Create initial default API key
        raw_key = generate_api_key()
        key_hash = hash_password(raw_key)
        key_prefix = raw_key[:14] + "..." + raw_key[-4:]
        
        try:
            cur.execute("""
            INSERT INTO `api_keys` (`user_id`, `name`, `key_hash`, `key_prefix`, `spend_limit`, `spent`, `is_active`)
            VALUES (%s, %s, %s, %s, 0.0, 0.0, 1)
            """, (user_id, "Основной ключ (Default)", key_hash, key_prefix))
            cnx.commit()
        except Exception:
            pass

        # Memory key fallback
        _memory_keys.setdefault(user_id, []).append({
            'id': 1,
            'user_id': user_id,
            'name': 'Основной ключ (Default)',
            'key_prefix': key_prefix,
            'spend_limit': 0.0,
            'spent': 0.0,
            'is_active': 1,
            'created_at': 'Сегодня'
        })

        # Record welcome bonus transaction
        tx_dict = {
            'id': 1,
            'user_id': user_id,
            'amount': initial_bonus,
            'type': 'bonus',
            'payment_method': 'system',
            'description': '🎁 Стартовый баланс при регистрации',
            'status': 'success',
            'reference_id': f"BONUS-{secrets.token_hex(4).upper()}",
            'created_at': 'Сегодня'
        }
        try:
            cur.execute("""
            INSERT INTO `transactions` (`user_id`, `amount`, `type`, `payment_method`, `description`, `status`, `reference_id`)
            VALUES (%s, %s, 'bonus', 'system', '🎁 Стартовый баланс при регистрации', 'success', %s)
            """, (user_id, initial_bonus, tx_dict['reference_id']))
            cnx.commit()
        except Exception:
            pass

        _memory_transactions.setdefault(user_id, []).insert(0, tx_dict)

        print(f"[MySQL SUCCESS] Зарегистрирован пользователь {clean_email} (ID: {user_id}) в базе `{DB_CONFIG['database']}`!")
        return {
            "id": user_id,
            "username": clean_name,
            "email": clean_email,
            "balance": initial_bonus,
            "initial_key": raw_key
        }

    finally:
        if cur: cur.close()
        if cnx and cnx.is_connected(): cnx.close()

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

    # 1. Update in memory store
    if user_id not in _memory_balances:
        _memory_balances[user_id] = {'balance': 150.0, 'total_spent': 0.0, 'total_deposited': 0.0}
    
    _memory_balances[user_id]['balance'] += total_credit
    _memory_balances[user_id]['total_deposited'] += amount
    new_bal = _memory_balances[user_id]['balance']

    # 2. Record in memory transactions
    tx_item = {
        'id': len(_memory_transactions.get(user_id, [])) + 1,
        'user_id': user_id,
        'amount': total_credit,
        'type': 'topup',
        'payment_method': method,
        'description': description,
        'status': 'success',
        'reference_id': tx_ref,
        'created_at': 'Сегодня'
    }
    _memory_transactions.setdefault(user_id, []).insert(0, tx_item)

    # 3. Try to update MySQL DB
    cnx = None
    cur = None
    try:
        cnx = get_connection()
        cur = cnx.cursor(buffered=True)
        try:
            cur.execute("""
            INSERT INTO `user_balances` (`user_id`, `balance`, `total_spent`, `total_deposited`)
            VALUES (%s, %s, 0.0, %s)
            ON DUPLICATE KEY UPDATE `balance` = `balance` + %s, `total_deposited` = `total_deposited` + %s
            """, (user_id, total_credit, amount, total_credit, amount))
            cnx.commit()
        except Exception:
            pass

        try:
            cur.execute("""
            INSERT INTO `transactions` (`user_id`, `amount`, `type`, `payment_method`, `description`, `status`, `reference_id`)
            VALUES (%s, %s, 'topup', %s, %s, 'success', %s)
            """, (user_id, total_credit, method, description, tx_ref))
            cnx.commit()
        except Exception:
            pass

    except Exception as e:
        print(f"[MySQL Notice] {e}")
    finally:
        if cur: cur.close()
        if cnx and cnx.is_connected(): cnx.close()

    return {
        "success": True,
        "credited": total_credit,
        "amount": amount,
        "bonus": bonus_rub,
        "new_balance": new_bal,
        "reference_id": tx_ref,
        "description": description
    }

def apply_promo_code(user_id: int, code_str: str) -> Dict[str, Any]:
    code_clean = code_str.strip().upper()
    
    promos = {
        "NEURO2026": 500.0,
        "WELCOME100": 100.0,
        "DEV500": 500.0,
        "DUCKAI": 250.0,
        "STARTAI": 300.0
    }

    if code_clean not in promos:
        return {"success": False, "error": "Промокод не найден или срок его действия истек"}

    if (user_id, code_clean) in _memory_used_promos:
        return {"success": False, "error": "Вы уже активировали этот промокод ранее"}

    bonus = promos[code_clean]
    _memory_used_promos.add((user_id, code_clean))

    # Update in memory
    if user_id not in _memory_balances:
        _memory_balances[user_id] = {'balance': 150.0, 'total_spent': 0.0, 'total_deposited': 0.0}
    _memory_balances[user_id]['balance'] += bonus
    new_bal = _memory_balances[user_id]['balance']

    tx_ref = f"PROMO-{secrets.token_hex(4).upper()}"
    desc = f"Активация промокода {code_clean} (+{bonus:.2f} ₽)"
    
    tx_item = {
        'id': len(_memory_transactions.get(user_id, [])) + 1,
        'user_id': user_id,
        'amount': bonus,
        'type': 'bonus',
        'payment_method': 'promo',
        'description': desc,
        'status': 'success',
        'reference_id': tx_ref,
        'created_at': 'Сегодня'
    }
    _memory_transactions.setdefault(user_id, []).insert(0, tx_item)

    # Try saving to MySQL
    cnx = None
    cur = None
    try:
        cnx = get_connection()
        cur = cnx.cursor(buffered=True)
        try:
            cur.execute("""
            INSERT INTO `user_balances` (`user_id`, `balance`, `total_spent`, `total_deposited`)
            VALUES (%s, %s, 0.0, 0.0)
            ON DUPLICATE KEY UPDATE `balance` = `balance` + %s
            """, (user_id, bonus, bonus))
            cnx.commit()
        except Exception:
            pass

        try:
            cur.execute("""
            INSERT INTO `transactions` (`user_id`, `amount`, `type`, `payment_method`, `description`, `status`, `reference_id`)
            VALUES (%s, %s, 'bonus', 'promo', %s, 'success', %s)
            """, (user_id, bonus, desc, tx_ref))
            cnx.commit()
        except Exception:
            pass
    except Exception:
        pass
    finally:
        if cur: cur.close()
        if cnx and cnx.is_connected(): cnx.close()

    return {
        "success": True,
        "bonus_amount": bonus,
        "new_balance": new_bal,
        "message": f"Промокод успешно активирован! Начислено {bonus:.2f} ₽"
    }

def debit_user_balance_for_api(user_id: int, cost: float, model_slug: str, prompt_tokens: int, comp_tokens: int, latency_ms: int = 150) -> bool:
    user = get_user_by_id(user_id)
    current_bal = (user.get('balance') or 0.0) if user else 0.0
    if current_bal < cost:
        return False

    # Update in memory
    if user_id not in _memory_balances:
        _memory_balances[user_id] = {'balance': current_bal, 'total_spent': 0.0, 'total_deposited': 0.0}
    
    _memory_balances[user_id]['balance'] = max(0.0, _memory_balances[user_id]['balance'] - cost)
    _memory_balances[user_id]['total_spent'] += cost

    tx_item = {
        'id': len(_memory_transactions.get(user_id, [])) + 1,
        'user_id': user_id,
        'amount': -cost,
        'type': 'usage',
        'payment_method': 'api_usage',
        'description': f"API запрос: {model_slug} ({prompt_tokens + comp_tokens} токенов)",
        'status': 'success',
        'reference_id': f"USG-{secrets.token_hex(4).upper()}",
        'created_at': 'Сегодня'
    }
    _memory_transactions.setdefault(user_id, []).insert(0, tx_item)

    # Try updating MySQL
    cnx = None
    cur = None
    try:
        cnx = get_connection()
        cur = cnx.cursor(buffered=True)
        try:
            cur.execute("""
            UPDATE `user_balances`
            SET `balance` = `balance` - %s, `total_spent` = `total_spent` + %s
            WHERE `user_id` = %s
            """, (cost, cost, user_id))
            cnx.commit()
        except Exception:
            pass
    except Exception:
        pass
    finally:
        if cur: cur.close()
        if cnx and cnx.is_connected(): cnx.close()

    return True

def get_user_transactions(user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    # Check MySQL first
    cnx = None
    cur = None
    try:
        cnx = get_connection()
        cur = cnx.cursor(dictionary=True, buffered=True)
        cur.execute("SELECT * FROM `transactions` WHERE `user_id` = %s ORDER BY `created_at` DESC, `id` DESC LIMIT %s", (user_id, limit))
        rows = cur.fetchall()
        if rows:
            return rows
    except Exception:
        pass
    finally:
        if cur: cur.close()
        if cnx and cnx.is_connected(): cnx.close()

    # In-memory transactions
    return _memory_transactions.get(user_id, [])[:limit]

def get_user_api_keys(user_id: int) -> List[Dict[str, Any]]:
    cnx = None
    cur = None
    try:
        cnx = get_connection()
        cur = cnx.cursor(dictionary=True, buffered=True)
        cur.execute("SELECT * FROM `api_keys` WHERE `user_id` = %s AND `is_active` = 1 ORDER BY `created_at` DESC", (user_id,))
        rows = cur.fetchall()
        if rows:
            return rows
    except Exception:
        pass
    finally:
        if cur: cur.close()
        if cnx and cnx.is_connected(): cnx.close()

    # In-memory keys
    keys = _memory_keys.get(user_id, [])
    if not keys:
        raw_key = generate_api_key()
        keys.append({
            'id': 1,
            'user_id': user_id,
            'name': 'Основной ключ (Default)',
            'key_prefix': raw_key[:14] + '...' + raw_key[-4:],
            'spend_limit': 0.0,
            'spent': 0.0,
            'is_active': 1,
            'created_at': 'Сегодня'
        })
        _memory_keys[user_id] = keys
    return keys

def create_user_api_key(user_id: int, name: str, spend_limit: float = 0.0) -> Dict[str, Any]:
    raw_key = generate_api_key()
    key_hash = hash_password(raw_key)
    key_prefix = raw_key[:14] + "..." + raw_key[-4:]
    key_name = name.strip() or "API Ключ"

    key_id = len(_memory_keys.get(user_id, [])) + 1
    new_key = {
        'id': key_id,
        'user_id': user_id,
        'name': key_name,
        'key_prefix': key_prefix,
        'spend_limit': spend_limit,
        'spent': 0.0,
        'is_active': 1,
        'created_at': 'Сегодня'
    }
    _memory_keys.setdefault(user_id, []).insert(0, new_key)

    cnx = None
    cur = None
    try:
        cnx = get_connection()
        cur = cnx.cursor(buffered=True)
        cur.execute("""
        INSERT INTO `api_keys` (`user_id`, `name`, `key_hash`, `key_prefix`, `spend_limit`, `spent`, `is_active`)
        VALUES (%s, %s, %s, %s, %s, 0.0, 1)
        """, (user_id, key_name, key_hash, key_prefix, spend_limit))
        cnx.commit()
    except Exception:
        pass
    finally:
        if cur: cur.close()
        if cnx and cnx.is_connected(): cnx.close()

    return {
        "id": key_id,
        "name": key_name,
        "raw_key": raw_key,
        "key_prefix": key_prefix,
        "spend_limit": spend_limit
    }

def delete_user_api_key(user_id: int, key_id: int) -> bool:
    if user_id in _memory_keys:
        _memory_keys[user_id] = [k for k in _memory_keys[user_id] if k.get('id') != key_id]

    cnx = None
    cur = None
    try:
        cnx = get_connection()
        cur = cnx.cursor(buffered=True)
        cur.execute("DELETE FROM `api_keys` WHERE `id` = %s AND `user_id` = %s", (key_id, user_id))
        cnx.commit()
    except Exception:
        pass
    finally:
        if cur: cur.close()
        if cnx and cnx.is_connected(): cnx.close()

    return True

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
