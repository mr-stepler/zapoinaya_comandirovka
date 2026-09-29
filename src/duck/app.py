import os
import time
import random
import re
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, g
from werkzeug.middleware.proxy_fix import ProxyFix

from duck import db

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "neuroapi-super-secret-key-2026-production")
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False

# Support reverse proxy headers (X-Forwarded-For, X-Forwarded-Proto, X-Forwarded-Host)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Initialize SQLite database on startup
db.init_db()

def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return db.get_user_by_id(user_id)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({"error": "Требуется авторизация"}), 401
            return redirect(url_for('login_page', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_user():
    user = get_current_user()
    return dict(current_user=user)

@app.after_request
def add_security_headers(response):
    response.headers['X-Frame-Options'] = 'ALLOWALL'
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Content-Security-Policy'] = "frame-ancestors *;"
    return response

# -------------------------------------------------------------
# WEB PAGES
# -------------------------------------------------------------

@app.route("/")
def index():
    user = get_current_user()
    models = db.get_all_models()
    return render_template('index.html', user=user, models=models)

@app.route("/login")
def login_page():
    if 'user_id' in session:
        return redirect(url_for('dashboard_page'))
    return render_template('login.html')

@app.route("/registration")
@app.route("/register")
def registration():
    if 'user_id' in session:
        return redirect(url_for('dashboard_page'))
    return render_template('registration.html')

@app.route("/welcome")
def welcome_page():
    name = request.args.get('name', session.get('user_name', 'Разработчик'))
    user = get_current_user()
    return render_template('welcome.html', name=name, user=user)

@app.route("/dashboard")
@login_required
def dashboard_page():
    user = get_current_user()
    models = db.get_all_models()
    api_keys = db.get_user_api_keys(user['id'])
    transactions = db.get_user_transactions(user['id'], limit=30)
    stats = db.get_user_stats(user['id'])
    return render_template('dashboard.html', user=user, models=models, api_keys=api_keys, transactions=transactions, stats=stats)

@app.route("/pricing")
def pricing_page():
    models = db.get_all_models()
    return render_template('pricing.html', models=models)

@app.route("/docs")
def docs_page():
    user = get_current_user()
    models = db.get_all_models()
    return render_template('docs.html', user=user, models=models)

# -------------------------------------------------------------
# AUTH API
# -------------------------------------------------------------

@app.route('/user_register', methods=['POST'])
@app.route('/api/register', methods=['POST'])
def user_register():
    req = request.get_json(silent=True) or request.form
    if not req:
        return jsonify({"error": "Отсутствуют данные запроса"}), 400

    name = req.get('name') or req.get('fullname') or ''
    email = req.get('email', '').strip().lower()
    password = req.get('password', '')
    promo = req.get('promo_code', '').strip()

    name = name.strip()
    if not name:
        name = email.split('@')[0] if '@' in email else "Пользователь"

    if not email or '@' not in email or '.' not in email:
        return jsonify({"error": "Введите корректный адрес электронной почты"}), 400

    if not password or len(password) < 4:
        return jsonify({"error": "Пароль должен содержать минимум 4 символа"}), 400

    existing = db.get_user_by_email(email)
    if existing:
        return jsonify({"error": "Пользователь с таким email уже зарегистрирован"}), 409

    password_hash = db.hash_password(password)
    
    try:
        user = db.create_user(name, email, password_hash, initial_bonus=150.0)
        initial_key = user.get('initial_key')
        
        # Apply promo code if provided during registration
        if promo:
            try:
                db.apply_promo_code(user['id'], promo)
                user = db.get_user_by_id(user['id'])
            except Exception:
                pass
        
        user['initial_key'] = initial_key

        session['user_id'] = user['id']
        session['user_name'] = user['username']
        session['user_email'] = user['email']

        return jsonify({
            "success": True,
            "message": "Регистрация успешно завершена! Вам начислен приветственный бонус 150 ₽.",
            "user": {
                "id": user['id'],
                "username": user['username'],
                "email": user['email'],
                "balance": user['balance']
            },
            "initial_key": user.get('initial_key'),
            "redirect": url_for('welcome_page', name=user['username'])
        }), 201

    except Exception as e:
        return jsonify({"error": f"Ошибка создания аккаунта: {str(e)}"}), 500

@app.route('/user_login', methods=['POST'])
@app.route('/api/login', methods=['POST'])
def user_login():
    req = request.get_json(silent=True) or request.form
    if not req or 'email' not in req or 'password' not in req:
        return jsonify({"error": "Заполните email и пароль"}), 400

    email = req['email'].strip().lower()
    password = req['password']

    user = db.get_user_by_email(email)
    if not user:
        return jsonify({"error": "Пользователь с таким email не найден"}), 401

    current_hash = db.hash_password(password)

    if current_hash == user['password_hash']:
        session['user_id'] = user['id']
        session['user_name'] = user['username']
        session['user_email'] = user['email']
        
        return jsonify({
            "success": True,
            "message": f"С возвращением, {user['username']}!",
            "user": {
                "id": user['id'],
                "username": user['username'],
                "email": user['email'],
                "balance": user['balance']
            },
            "redirect": url_for('dashboard_page')
        })
    else:
        return jsonify({"error": "Неверный пароль"}), 401

@app.route('/logout')
@app.route('/api/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    if request.is_json or request.method == 'POST':
        return jsonify({"success": True, "redirect": url_for('index')})
    return redirect(url_for('index'))

@app.route('/api/me')
def get_me():
    user = get_current_user()
    if not user:
        return jsonify({"authenticated": False}), 200
    stats = db.get_user_stats(user['id'])
    return jsonify({
        "authenticated": True,
        "user": stats
    })

# -------------------------------------------------------------
# BALANCE & BILLING API
# -------------------------------------------------------------

@app.route('/api/balance')
@login_required
def get_balance():
    user = get_current_user()
    return jsonify({
        "balance": user['balance'],
        "total_spent": user['total_spent'],
        "total_deposited": user['total_deposited'],
        "currency": "RUB",
        "symbol": "₽",
        "tier": user.get('tier', 'Developer')
    })

@app.route('/api/topup', methods=['POST'])
@login_required
def topup_balance():
    data = request.get_json() or {}
    try:
        amount = float(data.get('amount', 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Некорректная сумма пополнения"}), 400

    if amount < 50:
        return jsonify({"error": "Минимальная сумма пополнения — 50 ₽"}), 400
    if amount > 500000:
        return jsonify({"error": "Максимальная разовая сумма — 500 000 ₽"}), 400

    method = data.get('payment_method', 'sbp')
    user = get_current_user()

    try:
        result = db.add_user_balance(user['id'], amount, method=method)
        return jsonify({
            "success": True,
            "message": f"Баланс успешно пополнен на {result['credited']:.2f} ₽!",
            "credited": result['credited'],
            "bonus": result['bonus'],
            "new_balance": result['new_balance'],
            "reference_id": result['reference_id']
        })
    except Exception as e:
        return jsonify({"error": f"Ошибка обработки платежа: {str(e)}"}), 500

@app.route('/api/promo/apply', methods=['POST'])
@login_required
def promo_apply():
    data = request.get_json() or {}
    code = data.get('code', '').strip()
    if not code:
        return jsonify({"error": "Введите промокод"}), 400

    user = get_current_user()
    res = db.apply_promo_code(user['id'], code)
    if res.get('success'):
        return jsonify(res)
    else:
        return jsonify(res), 400

@app.route('/api/transactions')
@login_required
def get_transactions():
    user = get_current_user()
    limit = int(request.args.get('limit', 50))
    txs = db.get_user_transactions(user['id'], limit=limit)
    return jsonify({"transactions": txs})

# -------------------------------------------------------------
# API KEYS MANAGEMENT
# -------------------------------------------------------------

@app.route('/api/keys', methods=['GET'])
@login_required
def list_keys():
    user = get_current_user()
    keys = db.get_user_api_keys(user['id'])
    return jsonify({"keys": keys})

@app.route('/api/keys', methods=['POST'])
@login_required
def create_key():
    data = request.get_json() or {}
    name = data.get('name', '').strip() or f"Ключ #{random.randint(100, 999)}"
    spend_limit = float(data.get('spend_limit', 0.0) or 0.0)

    user = get_current_user()
    key_info = db.create_user_api_key(user['id'], name, spend_limit)
    return jsonify({
        "success": True,
        "message": "API ключ успешно сгенерирован",
        "key": key_info
    }), 201

@app.route('/api/keys/<int:key_id>', methods=['DELETE'])
@login_required
def delete_key(key_id):
    user = get_current_user()
    deleted = db.delete_user_api_key(user['id'], key_id)
    if deleted:
        return jsonify({"success": True, "message": "API ключ отозван"})
    return jsonify({"error": "Ключ не найден"}), 404

# -------------------------------------------------------------
# MODELS & PLAYGROUND API
# -------------------------------------------------------------

@app.route('/api/models')
def list_models():
    models = db.get_all_models()
    return jsonify({"models": models})

def generate_ai_response_mock(model_slug: str, prompt: str, system_prompt: str = ""):
    # Realistic latency simulation based on model type
    model_lower = model_slug.lower()
    
    # Prompt analysis to generate rich contextual answer
    p_lower = prompt.lower()
    
    if "image" in model_lower or "flux" in model_lower or "midjourney" in model_lower or "dall-e" in model_lower:
        # Image generation output
        image_seeds = [
            "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1000&q=80",
            "https://images.unsplash.com/photo-1634017839464-5c339ebe3cb4?auto=format&fit=crop&w=1000&q=80",
            "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=1000&q=80",
            "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1000&q=80"
        ]
        chosen_img = random.choice(image_seeds)
        return {
            "type": "image",
            "text": f"Изображение успешно сгенерировано по промпту: «{prompt}»\nРазрешение: 1024x1024, Steps: 28, CFG: 3.5, Seed: {random.randint(100000, 999999)}",
            "image_url": chosen_img,
            "prompt_tokens": len(prompt.split()) * 2,
            "completion_tokens": 100
        }
    
    if "code" in model_lower or "coder" in model_lower or "python" in p_lower or "код" in p_lower or "function" in p_lower or "скрипт" in p_lower:
        code_resp = f"""Вот оптимизированное решение на Python с использованием лучших практик:

```python
import asyncio
import aiohttp
from typing import List, Dict, Any

class NeuroAPIClient:
    def __init__(self, api_key: str, base_url: str = "https://api.neuroapi.io/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {{
            "Authorization": f"Bearer {{self.api_key}}",
            "Content-Type": "application/json"
        }}

    async def generate_completion(self, model: str, prompt: str) -> Dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            payload = {{
                "model": model,
                "messages": [{{"role": "user", "content": prompt}}],
                "temperature": 0.7
            }}
            async with session.post(f"{{self.base_url}}/chat/completions", json=payload, headers=self.headers) as resp:
                return await resp.json()

# Пример использования:
async def main():
    client = NeuroAPIClient(api_key="sk-neuro-sample-key")
    response = await client.generate_completion(
        model="{model_slug}",
        prompt="{prompt[:60]}..."
    )
    print("Ответ нейросети:", response)

if __name__ == "__main__":
    asyncio.run(main())
```

### Ключевые преимущества этого решения:
1. **Асинхронность**: Обработка сотен запросов без блокировки основного потока.
2. **Типизация**: Строгая валидация входящих и исходящих данных.
3. **Обработка ошибок**: Готовность к продакшн-нагрузкам.
"""
        return {
            "type": "text",
            "text": code_resp,
            "prompt_tokens": max(15, len(prompt.split()) * 2),
            "completion_tokens": 280
        }
        
    if "deepseek-reasoner" in model_lower or "o1" in model_lower or "reasoning" in model_lower:
        cot = f"""<think>
1. Анализ запроса пользователя: "{prompt}".
2. Выделение ключевых аспектов, терминов и целевого результата.
3. Оценка архитектурных альтернатив и возможных краевых случаев.
4. Синтез подробного структурированного ответа с практическими рекомендациями.
</think>

### Аналитический ответ модели {model_slug}:

В ответ на ваш запрос: **«{prompt}»**

1. **Суть концепции и архитектура:**
   При работе с распределенными AI-системами и LLM критически важно минимизировать задержку (latency) и контролировать расход токенов. Использование единого API-шлюза обеспечивает маршрутизацию запросов с балансировкой нагрузки и автоматическим failover.

2. **Пошаговый план реализации:**
   - **Шаг 1:** Интеграция API ключа через переменные окружения (`NEURO_API_KEY`).
   - **Шаг 2:** Настройка пула сессий для HTTP Keep-Alive соединений.
   - **Шаг 3:** Кэширование частых запросов (Embeddings / Redis) для экономии баланса до 40%.

3. **Результат и вывод:**
   Данная конфигурация гарантирует максимальную пропускную способность до 15 000 токенов/сек при стабильном пинге ~120мс."""
        return {
            "type": "text",
            "text": cot,
            "prompt_tokens": max(20, len(prompt.split()) * 2),
            "completion_tokens": 340
        }
        
    # Default text completion
    sample_text = f"""Здравствуйте! Я модель **{model_slug}**, подключенная через NeuroAPI.

По вашему запросу: *«{prompt}»*

Нейросеть успешно обработала контекст и сформировала детальный ответ:
• **Высокая точность**: Полное сохранение смысла и требований промпта.
• **Скорость отклика**: Запрос обработан на графических кластерах NVIDIA H100.
• **Готовность к интеграции**: Вы можете отправить аналогичный запрос через SDK на Python, Node.js или cURL.

Если вам требуется доработать ответ или сгенерировать программный код, просто укажите дополнительные параметры в промпте!"""

    return {
        "type": "text",
        "text": sample_text,
        "prompt_tokens": max(12, len(prompt.split()) * 2),
        "completion_tokens": 160
    }

@app.route('/api/playground/generate', methods=['POST'])
@login_required
def playground_generate():
    data = request.get_json() or {}
    model_slug = data.get('model', 'gpt-4o')
    prompt = data.get('prompt', '').strip()
    system_prompt = data.get('system_prompt', '').strip()

    if not prompt:
        return jsonify({"error": "Введите текст промпта"}), 400

    user = get_current_user()
    model = db.get_model_by_slug(model_slug)
    if not model:
        model = db.get_all_models()[0]
        model_slug = model['slug']

    # Simulate realistic execution time
    start_time = time.time()
    
    # Calculate costs
    ai_result = generate_ai_response_mock(model_slug, prompt, system_prompt)
    prompt_tokens = ai_result['prompt_tokens']
    completion_tokens = ai_result['completion_tokens']
    
    if model['category'] == 'image':
        cost = model['price_input_1m'] # fixed cost per image
    elif model['category'] == 'audio':
        cost = model['price_input_1m'] # fixed cost per minute
    else:
        cost = (prompt_tokens * model['price_input_1m'] + completion_tokens * model['price_output_1m']) / 1_000_000.0
        cost = max(round(cost, 4), 0.001)

    # Check if balance is enough
    if user['balance'] < cost:
        return jsonify({
            "error": f"Недостаточно средств на балансе. Требуется {cost:.3f} ₽, текущий баланс: {user['balance']:.2f} ₽. Пополните баланс в разделе «Финансы».",
            "insufficient_balance": True
        }), 402

    latency_ms = int((time.time() - start_time) * 1000) + model.get('latency_ms', 180) + random.randint(10, 40)
    
    # Debit balance
    db.debit_user_balance_for_api(user['id'], cost, model_slug, prompt_tokens, completion_tokens, latency_ms)
    
    updated_user = db.get_user_by_id(user['id'])

    return jsonify({
        "success": True,
        "model": model_slug,
        "model_name": model['name'],
        "output_type": ai_result.get('type', 'text'),
        "text": ai_result.get('text', ''),
        "image_url": ai_result.get('image_url', ''),
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost_rub": cost
        },
        "latency_ms": latency_ms,
        "new_balance": updated_user['balance']
    })

# OpenAI compatible endpoint
@app.route('/v1/chat/completions', methods=['POST'])
def openai_chat_completions():
    auth_header = request.headers.get('Authorization', '')
    raw_key = auth_header.replace('Bearer ', '').strip()
    
    user = None
    if raw_key:
        key_hash = db.hash_password(raw_key)
        conn = db.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT u.* FROM users u JOIN api_keys k ON u.id = k.user_id WHERE k.key_hash = ? AND k.is_active = 1", (key_hash,))
        user_row = cur.fetchone()
        conn.close()
        if user_row:
            user = dict(user_row)
    
    if not user:
        user = get_current_user()
        
    if not user:
        return jsonify({"error": {"message": "Неверный API ключ или отсутствует авторизация", "type": "invalid_request_error"}}), 401

    data = request.get_json() or {}
    model_slug = data.get('model', 'gpt-4o')
    messages = data.get('messages', [])
    
    prompt = " ".join([m.get('content', '') for m in messages if isinstance(m, dict)])
    if not prompt:
        prompt = "Hello"

    model = db.get_model_by_slug(model_slug) or db.get_all_models()[0]
    
    ai_result = generate_ai_response_mock(model_slug, prompt)
    prompt_tokens = ai_result['prompt_tokens']
    completion_tokens = ai_result['completion_tokens']
    cost = (prompt_tokens * model['price_input_1m'] + completion_tokens * model['price_output_1m']) / 1_000_000.0
    cost = max(round(cost, 4), 0.001)

    if user['balance'] < cost:
        return jsonify({"error": {"message": "Недостаточно средств на балансе NeuroAPI. Пополните счет.", "type": "insufficient_quota"}}), 402

    db.debit_user_balance_for_api(user['id'], cost, model_slug, prompt_tokens, completion_tokens, 180)

    return jsonify({
        "id": f"chatcmpl-{random.randint(10000000, 99999999)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_slug,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": ai_result.get('text', '')
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens
        }
    })

@app.route('/v1/models', methods=['GET'])
def openai_models():
    models = db.get_all_models()
    return jsonify({
        "object": "list",
        "data": [{
            "id": m["slug"],
            "object": "model",
            "created": 1700000000,
            "owned_by": m["provider"]
        } for m in models]
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
