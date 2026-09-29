$(document).ready(function(){
    $('#67').on('submit', function(e){
        e.preventDefault();
        err = 0;

        // Определяем, какая это форма: регистрация или вход
        var isRegistration = $('#confirm_password').length > 0;

        if (isRegistration) {
            // ---- Регистрация ----
            if ($('#fullname').val().trim() === '' ||
                $('#email').val().trim() === '' ||
                $('#password').val().trim() === '' ||
                $('#password').val().trim() != $('#confirm_password').val().trim()){
                err = 1;
                alert('Проверьте заполнение полей и совпадение паролей');
            }

            if (err == 0){
                $.ajax({
                    url: '/user_register',
                    method: 'POST',
                    contentType: 'application/json',
                    data: JSON.stringify({
                        name: $('#fullname').val(),
                        password: $('#password').val(),
                        email: $('#email').val()
                    })
                }).done(function(){
                    var name = $('#fullname').val();
                    window.location.href = "/welcome?name=" + encodeURIComponent(name);
                }).fail(function(xhr){
                    alert(xhr.responseJSON?.error || 'Ошибка регистрации');
                });
            }
        } else {
            // ---- Вход ----
            if ($('#email').val().trim() === '' || $('#password').val().trim() === ''){
                err = 1;
                alert('Заполните все поля');
            }

            if (err == 0){
                $.ajax({
                    url: '/user_login',
                    method: 'POST',
                    contentType: 'application/json',
                    data: JSON.stringify({
                        email: $('#email').val(),
                        password: $('#password').val()
                    })
                }).done(function(response){
                    window.location.href = "/";
                }).fail(function(xhr){
                    alert(xhr.responseJSON?.error || 'Ошибка входа');
                });
            }
        }
    });
});