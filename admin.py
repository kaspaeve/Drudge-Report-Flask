from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_required
from models import db, NewsSource, Article

admin_panel = Blueprint("admin_panel", __name__)

@admin_panel.route("/admin")
@login_required
def dashboard():
    sources = NewsSource.query.all()
    return render_template("admin.html", sources=sources)

@admin_panel.route("/admin/add_source", methods=["POST"])
@login_required
def add_source():
    name = request.form["name"]
    url = request.form["url"]
    scraping_type = request.form["scraping_type"]
    new_source = NewsSource(name=name, url=url, scraping_type=scraping_type)
    db.session.add(new_source)
    db.session.commit()
    return redirect(url_for("admin_panel.dashboard"))

@admin_panel.route("/admin/delete_source/<int:id>")
@login_required
def delete_source(id):
    source = NewsSource.query.get(id)
    db.session.delete(source)
    db.session.commit()
    return redirect(url_for("admin_panel.dashboard"))
