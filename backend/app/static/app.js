/* Deadlines page: add confirmation to delete forms. */
(function () {
    "use strict";
    document.addEventListener("DOMContentLoaded", function () {
        var forms = document.querySelectorAll("form.delete-form");
        for (var i = 0; i < forms.length; i++) {
            forms[i].addEventListener("submit", function (e) {
                if (!confirm("Weet je zeker dat je deze deadline wilt verwijderen?")) {
                    e.preventDefault();
                }
            });
        }
    });
})();
