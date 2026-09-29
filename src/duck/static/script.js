// Auth forms handler (Login / Registration)
$(document).ready(function(){
    $('#auth-form, #67').on('submit', function(e){
        e.preventDefault();
        
        var isRegistration = $('#confirm_password').length > 0;
        var submitBtn = $(this).find('button[type="submit"]');
        var originalBtnText = submitBtn.text();

        if (isRegistration) {
            // ---- Регистрация ----
            var name = $('#fullname').val().trim();
            var email = $('#email').val().trim();
            var password = $('#password').val().trim();
            var confirmPassword = $('#confirm_password').val().trim();
            var promo = $('#promo_code').length ? $('#promo_code').val().trim() : '';

            if (name === '' || email === '' || password === '') {
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
                    showToast('Пароль должен содержать от 4 символов', 'error');
                } else {
                    alert('Пароль должен содержать от 4 символов');
                }
                return;
            }

            submitBtn.prop('disabled', true).text('Регистрация...');

            $.ajax({
                url: '/user_register',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({
                    name: name,
                    email: email,
                    password: password,
                    promo_code: promo
                })
            }).done(function(res){
                if (typeof showToast === 'function') {
                    showToast('Регистрация успешна! Начислен бонус 150 ₽', 'success');
                }
                window.location.href = res.redirect || ("/welcome?name=" + encodeURIComponent(name));
            }).fail(function(xhr){
                submitBtn.prop('disabled', false).text(originalBtnText);
                var err = xhr.responseJSON?.error || 'Ошибка при регистрации';
                if (typeof showToast === 'function') {
                    showToast(err, 'error');
                } else {
                    alert(err);
                }
            });

        } else {
            // ---- Вход ----
            var loginEmail = $('#email').val().trim();
            var loginPassword = $('#password').val().trim();

            if (loginEmail === '' || loginPassword === '') {
                if (typeof showToast === 'function') {
                    showToast('Введите email и пароль', 'error');
                } else {
                    alert('Введите email и пароль');
                }
                return;
            }

            submitBtn.prop('disabled', true).text('Вход в систему...');

            $.ajax({
                url: '/user_login',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({
                    email: loginEmail,
                    password: loginPassword
                })
            }).done(function(response){
                if (typeof showToast === 'function') {
                    showToast(response.message || 'Успешный вход!', 'success');
                }
                window.location.href = response.redirect || "/dashboard";
            }).fail(function(xhr){
                submitBtn.prop('disabled', false).text(originalBtnText);
                var err = xhr.responseJSON?.error || 'Неверный логин или пароль';
                if (typeof showToast === 'function') {
                    showToast(err, 'error');
                } else {
                    alert(err);
                }
            });
        }
    });
});
