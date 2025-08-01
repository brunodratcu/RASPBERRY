from flask import Blueprint, render_template, request, redirect, session
from auth.utils import check_password, get_hashed_password, init_db, insert_event
import datetime

auth_bp = Blueprint("auth", __name__)

# Simula um usuário salvo
USERS = {
    "admin": get_hashed_password("admin")
}

@auth_bp.route("/", methods=["GET", "POST"])
def home():
    error = None

    # Login
    if request.method == "POST":
        if "username" in request.form and "password" in request.form:
            username = request.form["username"]
            password = request.form["password"]

            if username in USERS and check_password(password, USERS[username]):
                session["user"] = username
            else:
                error = "Usuário ou senha inválido"

        elif "event_name" in request.form:
            # Cadastro de evento
            if "user" in session:
                name = request.form["event_name"]
                date = request.form["event_date"]
                time = request.form["event_time"]
                insert_event(name, date, time)
            else:
                error = "Faça login primeiro"

    today = datetime.date.today().isoformat()
    return render_template("home.html", user=session.get("user"), error=error, today=today)
