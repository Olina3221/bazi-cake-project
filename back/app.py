from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
import db

app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
    return render_template("order_form.html")


@app.route("/submit", methods=["POST"])
def submit():
    name      = request.form.get("name", "").strip()
    phone     = request.form.get("phone", "").strip()
    birthday  = request.form.get("birthday", "").strip()
    shichen   = request.form.get("shichen", "不填").strip()
    wish_main = request.form.get("wish_main", "").strip()
    wish_sub  = request.form.get("wish_sub", "").strip()
    note      = request.form.get("note", "").strip()

    if not name or not birthday or not wish_main:
        return "❌ 請填寫必填欄位（姓名、生日、心願）", 400

    try:
        new_id = db.create_order(name, phone, birthday, shichen, wish_main, wish_sub, note)
    except Exception as e:
        return f"❌ 寫入失敗：{e}", 500

    return redirect(url_for("success", name=name, order_id=new_id))


@app.route("/success")
def success():
    name     = request.args.get("name", "")
    order_id = request.args.get("order_id", "")
    return render_template("success.html", name=name, order_id=order_id)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
