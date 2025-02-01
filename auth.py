from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from werkzeug.security import check_password_hash
from models import db, User

auth = Blueprint("auth", __name__)


@auth.route("/setup", methods=["GET", "POST"])
def setup():
    admin_exists = User.query.filter_by(is_admin=True).first()
    if admin_exists:
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            flash("Username and password required!", "danger")
            return redirect(url_for("auth.setup"))

        new_admin = User(username=username, is_admin=True)
        new_admin.set_password(password)

        db.session.add(new_admin)
        db.session.commit()
        flash("Admin account created! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("setup.html")


@auth.route("/login", methods=["GET", "POST"])
def login():
    admin_exists = User.query.filter_by(is_admin=True).first()
    if not admin_exists:
        return redirect(url_for("auth.setup"))  

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("home"))
        else:
            flash("Invalid credentials", "danger")

    return render_template("login.html")


@auth.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully", "success")
    return redirect(url_for("auth.login"))
