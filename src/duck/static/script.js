// Native Vanilla JS Auth Forms Handler (No jQuery required)
document.addEventListener('DOMContentLoaded', function () {
    const authForm = document.getElementById('auth-form') || document.getElementById('67');
    if (!authForm) return;

    authForm.addEventListener('submit', async function (e) {
        e.preventDefault();

        const isRegistration = !!document.getElementById('confirm_password');
        const submitBtn = authForm.querySelector('button[type="submit"]');
        const originalBtnText = submitBtn ? submitBtn.innerText : '';

        if (isRegistration) {
            const fullnameElem = document.getElementById('fullname');
            const emailElem = document.getElementById('email');
            const passwordElem = document.getElementById('password');
            const confirmPassElem = document.getElementById('confirm_password');
            const promoElem = document.getElementById('promo_code');

            const name = fullnameElem ? fullnameElem.value.trim() : '';
            const email = emailElem ? emailElem.value.trim() : '';
            const password = passwordElem ? passwordElem.value.trim() : '';
            const confirmPassword = confirmPassElem ? confirmPassElem.value.trim() : '';
            const promo = promoElem ? promoElem.value.trim() : '';

            if (!name || !email || !password) {
                if (typeof showToast === 'function') {
                    showToast('Заполните все обязательные поля', 'error');
                } else {
                    alert('Заполните все обязательные поля');
                }
                return;
            }

            if (password !== confirmPassword) {
                if (typeof showToast === 'function') {
                    showToast('Пароли не совпадают', 'error');
                } else {
                    alert('Пароли не совпадают');
                }
                return;
            }

            if (password.length < 4) {
                if (typeof showToast === 'function') {
                    showToast('Пароль должен быть не менее 4 символов', 'error');
                } else {
                    alert('Пароль должен быть не менее 4 символов');
                }
                return;
            }

            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerText = 'Регистрация...';
            }

            try {
                const res = await fetch('/user_register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: name,
                        email: email,
                        password: password,
                        promo_code: promo
                    })
                });

                const data = await res.json();
                if (res.ok && data.success) {
                    if (typeof showToast === 'function') {
                        showToast('Регистрация успешна! Начислен бонус 150 ₽', 'success');
                    }
                    window.location.href = data.redirect || ('/welcome?name=' + encodeURIComponent(name));
                } else {
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        submitBtn.innerText = originalBtnText;
                    }
                    const err = data.error || 'Ошибка регистрации';
                    if (typeof showToast === 'function') {
                        showToast(err, 'error');
                    } else {
                        alert(err);
                    }
                }
            } catch (err) {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerText = originalBtnText;
                }
                if (typeof showToast === 'function') {
                    showToast('Ошибка сети при регистрации', 'error');
                } else {
                    alert('Ошибка сети при регистрации');
                }
            }

        } else {
            // Login flow
            const emailElem = document.getElementById('email');
            const passwordElem = document.getElementById('password');

            const email = emailElem ? emailElem.value.trim() : '';
            const password = passwordElem ? passwordElem.value.trim() : '';

            if (!email || !password) {
                if (typeof showToast === 'function') {
                    showToast('Введите email и пароль', 'error');
                } else {
                    alert('Введите email и пароль');
                }
                return;
            }

            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerText = 'Вход...';
            }

            try {
                const res = await fetch('/user_login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        email: email,
                        password: password
                    })
                });

                const data = await res.json();
                if (res.ok && data.success) {
                    if (typeof showToast === 'function') {
                        showToast(data.message || 'Успешный вход!', 'success');
                    }
                    window.location.href = data.redirect || '/dashboard';
                } else {
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        submitBtn.innerText = originalBtnText;
                    }
                    const err = data.error || 'Неверный email или пароль';
                    if (typeof showToast === 'function') {
                        showToast(err, 'error');
                    } else {
                        alert(err);
                    }
                }
            } catch (err) {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerText = originalBtnText;
                }
                if (typeof showToast === 'function') {
                    showToast('Ошибка сети при входе', 'error');
                } else {
                    alert('Ошибка сети при входе');
                }
            }
        }
    });
});
