// NeuroAPI Core Frontend Script

function showToast(message, type = 'success') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    const icon = type === 'success' 
        ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>`
        : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fb7185" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;

    toast.innerHTML = `${icon}<span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(40px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function copyToClipboard(text, successMsg = 'Скопировано в буфер обмена!') {
    navigator.clipboard.writeText(text).then(() => {
        showToast(successMsg, 'success');
    }).catch(() => {
        // Fallback
        const el = document.createElement('textarea');
        el.value = text;
        document.body.appendChild(el);
        el.select();
        document.execCommand('copy');
        document.body.removeChild(el);
        showToast(successMsg, 'success');
    });
}

// -------------------------------------------------------------
// TOP-UP & BILLING MODAL LOGIC
// -------------------------------------------------------------
let selectedTopupAmount = 1000;
let selectedPaymentMethod = 'sbp';

function openTopupModal(defaultAmount = 1000) {
    const modal = document.getElementById('topupModal');
    if (!modal) return;
    
    selectedTopupAmount = defaultAmount;
    updateTopupCalculation();
    modal.classList.add('active');
}

function closeTopupModal() {
    const modal = document.getElementById('topupModal');
    if (modal) modal.classList.remove('active');
}

function selectPreset(amount, elem) {
    selectedTopupAmount = amount;
    document.querySelectorAll('.preset-chip').forEach(c => c.classList.remove('selected'));
    if (elem) elem.classList.add('selected');
    
    const customInput = document.getElementById('customAmountInput');
    if (customInput) customInput.value = amount;
    
    updateTopupCalculation();
}

function onCustomAmountChange(val) {
    const num = parseFloat(val) || 0;
    selectedTopupAmount = num;
    document.querySelectorAll('.preset-chip').forEach(c => c.classList.remove('selected'));
    updateTopupCalculation();
}

function selectPaymentMethod(method, elem) {
    selectedPaymentMethod = method;
    document.querySelectorAll('.pm-card').forEach(c => c.classList.remove('selected'));
    if (elem) elem.classList.add('selected');
}

function updateTopupCalculation() {
    const amount = selectedTopupAmount;
    let bonusPct = 0;
    if (amount >= 10000) bonusPct = 0.15;
    else if (amount >= 5000) bonusPct = 0.10;
    else if (amount >= 2500) bonusPct = 0.05;

    const bonusRub = Math.round(amount * bonusPct);
    const totalCredit = amount + bonusRub;

    const summaryTotal = document.getElementById('topupSummaryTotal');
    const summaryBonus = document.getElementById('topupSummaryBonus');
    
    if (summaryTotal) summaryTotal.textContent = `${totalCredit.toLocaleString('ru-RU')} ₽`;
    if (summaryBonus) {
        if (bonusRub > 0) {
            summaryBonus.textContent = `+${bonusRub.toLocaleString('ru-RU')} ₽ (Бонус ${(bonusPct*100)}%)`;
            summaryBonus.style.display = 'inline';
        } else {
            summaryBonus.style.display = 'none';
        }
    }
}

async function executeTopup() {
    const amount = selectedTopupAmount;
    if (!amount || amount < 50) {
        showToast('Минимальная сумма пополнения — 50 ₽', 'error');
        return;
    }

    const btn = document.getElementById('btnSubmitTopup');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner"></span> Обработка платежа...`;
    }

    try {
        const res = await fetch('/api/topup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                amount: amount,
                payment_method: selectedPaymentMethod
            })
        });

        const data = await res.json();
        if (res.ok && data.success) {
            showToast(data.message || `Баланс успешно пополнен на ${data.credited} ₽!`, 'success');
            
            // Update balance indicators across the UI
            updateBalanceUI(data.new_balance);
            
            closeTopupModal();
            
            // If on dashboard, dynamically reload transactions or table
            if (typeof reloadDashboardData === 'function') {
                reloadDashboardData();
            } else {
                setTimeout(() => window.location.reload(), 1200);
            }
        } else {
            showToast(data.error || 'Ошибка при пополнении', 'error');
        }
    } catch (err) {
        showToast('Сетевая ошибка при проведении платежа', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `Пополнить баланс`;
        }
    }
}

function updateBalanceUI(newBalance) {
    const formatted = parseFloat(newBalance).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    document.querySelectorAll('.user-balance-value').forEach(el => {
        el.textContent = `${formatted} ₽`;
    });
}

// -------------------------------------------------------------
// PROMO CODE ACTIVATION
// -------------------------------------------------------------
async function applyPromoCode() {
    const input = document.getElementById('promoCodeInput');
    if (!input || !input.value.trim()) {
        showToast('Введите промокод', 'error');
        return;
    }

    const code = input.value.trim();
    const btn = document.getElementById('btnApplyPromo');
    if (btn) btn.disabled = true;

    try {
        const res = await fetch('/api/promo/apply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: code })
        });
        const data = await res.json();

        if (res.ok && data.success) {
            showToast(data.message, 'success');
            input.value = '';
            updateBalanceUI(data.new_balance);
            if (typeof reloadDashboardData === 'function') {
                reloadDashboardData();
            } else {
                setTimeout(() => window.location.reload(), 1200);
            }
        } else {
            showToast(data.error || 'Неверный промокод', 'error');
        }
    } catch (e) {
        showToast('Ошибка при активации промокода', 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

// -------------------------------------------------------------
// API KEY MANAGEMENT
// -------------------------------------------------------------
function openCreateKeyModal() {
    const modal = document.getElementById('createKeyModal');
    if (modal) modal.classList.add('active');
}

function closeCreateKeyModal() {
    const modal = document.getElementById('createKeyModal');
    if (modal) modal.classList.remove('active');
}

async function submitCreateKey() {
    const nameInput = document.getElementById('keyNameInput');
    const limitInput = document.getElementById('keyLimitInput');
    const name = nameInput ? nameInput.value.trim() : '';
    const limit = limitInput ? parseFloat(limitInput.value) || 0 : 0;

    try {
        const res = await fetch('/api/keys', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, spend_limit: limit })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            closeCreateKeyModal();
            showKeyCreatedSuccessModal(data.key.raw_key, data.key.name);
        } else {
            showToast(data.error || 'Ошибка создания ключа', 'error');
        }
    } catch (e) {
        showToast('Ошибка сети при создании ключа', 'error');
    }
}

function showKeyCreatedSuccessModal(rawKey, keyName) {
    const modal = document.getElementById('keyCreatedModal');
    if (!modal) {
        showToast('Ключ создан! Скопируйте: ' + rawKey, 'success');
        setTimeout(() => window.location.reload(), 1500);
        return;
    }
    
    document.getElementById('newRawKeyValue').textContent = rawKey;
    document.getElementById('newKeyNameLabel').textContent = keyName || 'Новый ключ';
    modal.classList.add('active');
}

function closeKeyCreatedModal() {
    const modal = document.getElementById('keyCreatedModal');
    if (modal) modal.classList.remove('active');
    window.location.reload();
}

async function deleteApiKey(keyId) {
    if (!confirm('Вы уверены, что хотите отозвать этот API ключ? Все приложения, использующие его, потеряют доступ.')) {
        return;
    }

    try {
        const res = await fetch(`/api/keys/${keyId}`, {
            method: 'DELETE'
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast('API ключ успешно отозван', 'success');
            const row = document.getElementById(`key-row-${keyId}`);
            if (row) row.remove();
            else window.location.reload();
        } else {
            showToast(data.error || 'Ошибка удаления', 'error');
        }
    } catch (e) {
        showToast('Ошибка при удалении ключа', 'error');
    }
}

// -------------------------------------------------------------
// PLAYGROUND GENERATION
// -------------------------------------------------------------
async function runPlaygroundPrompt() {
    const promptInput = document.getElementById('playgroundPrompt');
    const modelSelect = document.getElementById('playgroundModel');
    const systemPromptInput = document.getElementById('playgroundSystemPrompt');
    const outputElem = document.getElementById('playgroundOutput');
    const btn = document.getElementById('btnRunPlayground');
    const metricsTokens = document.getElementById('metricTokens');
    const metricsCost = document.getElementById('metricCost');
    const metricsLatency = document.getElementById('metricLatency');

    if (!promptInput || !promptInput.value.trim()) {
        showToast('Введите промпт для нейросети', 'error');
        return;
    }

    const prompt = promptInput.value.trim();
    const model = modelSelect ? modelSelect.value : 'gpt-4o';
    const systemPrompt = systemPromptInput ? systemPromptInput.value.trim() : '';

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<svg class="spin-anim" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10" stroke-opacity="0.25"/><path d="M12 2a10 10 0 0 1 10 10"/></svg> Генерация ответа...`;
    }

    if (outputElem) {
        outputElem.innerHTML = `<span style="color: #94a3b8;">Отправка запроса к кластеру <strong>${model}</strong>... Ожидание токенов...</span>`;
    }

    try {
        const res = await fetch('/api/playground/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: model,
                prompt: prompt,
                system_prompt: systemPrompt
            })
        });

        const data = await res.json();
        if (res.ok && data.success) {
            if (data.output_type === 'image' && data.image_url) {
                outputElem.innerHTML = `
                    <div style="margin-bottom: 12px; color: #34d399; font-weight: 600;">✓ Изображение сгенерировано (${data.model_name}):</div>
                    <img src="${data.image_url}" alt="AI generated" style="max-width: 100%; border-radius: 12px; border: 1px solid rgba(255,255,255,0.15); box-shadow: 0 10px 30px rgba(0,0,0,0.5);"/>
                    <div style="margin-top: 10px; font-size: 13px; color: #94a3b8;">${escapeHtml(data.text)}</div>
                `;
            } else {
                outputElem.textContent = data.text;
            }

            if (metricsTokens) metricsTokens.textContent = `${data.usage.total_tokens} ток.`;
            if (metricsCost) metricsCost.textContent = `${data.usage.cost_rub.toFixed(4)} ₽`;
            if (metricsLatency) metricsLatency.textContent = `${data.latency_ms} ms`;

            // Update user balance UI
            updateBalanceUI(data.new_balance);
            showToast(`Успешно! Списано: ${data.usage.cost_rub.toFixed(4)} ₽`, 'success');

        } else if (res.status === 402 || data.insufficient_balance) {
            outputElem.innerHTML = `<span style="color: #fb7185;">⚠️ ${data.error}</span>`;
            showToast('Недостаточно средств на балансе. Пополните счет.', 'error');
            openTopupModal();
        } else if (res.status === 401) {
            outputElem.innerHTML = `<span style="color: #fb7185;">Требуется авторизация. Войдите в аккаунт.</span>`;
            showToast('Войдите в аккаунт для использования Playground', 'error');
            setTimeout(() => window.location.href = '/login', 1500);
        } else {
            outputElem.textContent = `Ошибка: ${data.error || 'Не удалось получить ответ'}`;
            showToast(data.error || 'Ошибка запроса', 'error');
        }
    } catch (e) {
        outputElem.textContent = 'Ошибка сети при обращении к API';
        showToast('Ошибка сети', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Запустить запрос (Ctrl + Enter)`;
        }
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// -------------------------------------------------------------
// FILTERING MODELS
// -------------------------------------------------------------
function filterModels(category, pillElem) {
    document.querySelectorAll('.cat-pill').forEach(p => p.classList.remove('active'));
    if (pillElem) pillElem.classList.add('active');

    const searchVal = (document.getElementById('modelSearchInput')?.value || '').toLowerCase();
    
    document.querySelectorAll('.model-card').forEach(card => {
        const cardCat = card.getAttribute('data-category');
        const cardName = (card.getAttribute('data-name') || '').toLowerCase();
        const cardProvider = (card.getAttribute('data-provider') || '').toLowerCase();
        
        const matchesCat = (category === 'all' || cardCat === category);
        const matchesSearch = (!searchVal || cardName.includes(searchVal) || cardProvider.includes(searchVal));

        if (matchesCat && matchesSearch) {
            card.style.display = 'flex';
        } else {
            card.style.display = 'none';
        }
    });
}

function searchModels(val) {
    const activeCat = document.querySelector('.cat-pill.active')?.getAttribute('data-category') || 'all';
    filterModels(activeCat, null);
}

// -------------------------------------------------------------
// CODE SNIPPET TABS
// -------------------------------------------------------------
const codeSnippets = {
    python: `import openai

client = openai.OpenAI(
    api_key="sk-neuro-YOUR_API_KEY",
    base_url="https://api.neuroapi.io/v1"
)

response = client.chat.completions.create(
    model="gpt-4o",  # или claude-3-5-sonnet, deepseek-chat-v3, flux-1-schnell
    messages=[
        {"role": "system", "content": "Ты экспертный AI-ассистент."},
        {"role": "user", "content": "Напиши архитектуру высоконагруженного сервиса."}
    ],
    temperature=0.7
)

print(response.choices[0].message.content)`,

    javascript: `import OpenAI from "openai";

const openai = new OpenAI({
  apiKey: "sk-neuro-YOUR_API_KEY",
  baseURL: "https://api.neuroapi.io/v1",
});

async function main() {
  const completion = await openai.chat.completions.create({
    model: "claude-3-5-sonnet",
    messages: [{ role: "user", content: "Привет! Напиши код на React." }],
  });

  console.log(completion.choices[0].message.content);
}

main();`,

    curl: `curl https://api.neuroapi.io/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer sk-neuro-YOUR_API_KEY" \\
  -d '{
    "model": "deepseek-reasoner-r1",
    "messages": [
      {"role": "user", "content": "Реши сложную логическую задачу..."}
    ]
  }'`,

    php: `<?php
$ch = curl_init("https://api.neuroapi.io/v1/chat/completions");
curl_setopt($ch, CURLOPT_HTTPHEADER, [
    'Content-Type: application/json',
    'Authorization: Bearer sk-neuro-YOUR_API_KEY'
]);
curl_setopt($ch, CURLOPT_POST, 1);
curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode([
    'model' => 'gpt-4o-mini',
    'messages' => [['role' => 'user', 'content' => 'Привет, NeuroAPI!']]
]));
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
$response = curl_exec($ch);
curl_close($ch);

echo $response;`,

    go: `package main

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
)

func main() {
	jsonData := []byte(\`{
		"model": "deepseek-chat-v3",
		"messages": [{"role": "user", "content": "Hello from Golang!"}]
	}\`)

	req, _ := http.NewRequest("POST", "https://api.neuroapi.io/v1/chat/completions", bytes.NewBuffer(jsonData))
	req.Header.Set("Authorization", "Bearer sk-neuro-YOUR_API_KEY")
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{}
	resp, _ := client.Do(req)
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	fmt.Println(string(body))
}`
};

function switchCodeTab(lang, elem) {
    document.querySelectorAll('.code-tab').forEach(t => t.classList.remove('active'));
    if (elem) elem.classList.add('active');

    const codeBody = document.getElementById('codeShowcaseBody');
    if (codeBody && codeSnippets[lang]) {
        codeBody.textContent = codeSnippets[lang];
    }
}

// Global keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        const promptInput = document.getElementById('playgroundPrompt');
        if (promptInput && document.activeElement === promptInput) {
            runPlaygroundPrompt();
        }
    }
    if (e.key === 'Escape') {
        closeTopupModal();
        closeCreateKeyModal();
    }
});
