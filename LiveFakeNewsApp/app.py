from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import pickle
import webbrowser
from threading import Timer

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ================= DATABASE =================
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ================= MODELS =================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default="user")
    status = db.Column(db.String(20), default="pending")

class AdminLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(200))
    username = db.Column(db.String(100))

# ================= LOAD ML MODEL =================
model = pickle.load(open("model.pkl", "rb"))
vectorizer = pickle.load(open("vectorizer.pkl", "rb"))

API_KEY = "e6c91e4d48674013a395e00b49689bbe"

# ================= AUTO OPEN BROWSER =================
def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000/")

# ================= NEWS FUNCTION =================
def get_news(category="general", query=None):
    if query:
        url = f"https://newsapi.org/v2/everything?q={query}&apiKey={API_KEY}&pageSize=10"
    else:
        url = f"https://newsapi.org/v2/top-headlines?country=in&category={category}&apiKey={API_KEY}&pageSize=10"

    res = requests.get(url).json()
    news_list = []

    for a in res.get("articles", []):
        text = (a.get("title", "") + " " + str(a.get("description", "")))
        vect = vectorizer.transform([text])
        prob = model.predict_proba(vect)[0][1]

        news_list.append({
            "title": a.get("title", ""),
            "source": a["source"]["name"],
            "image": a.get("urlToImage"),
            "result": "REAL" if prob > 0.5 else "FAKE",
            "probability": round(prob * 100, 2)
        })

    return news_list

# ================= REGISTER =================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        if User.query.filter_by(username=request.form["username"]).first():
            return render_template(
                "register.html",
                message="User already exists",
                success=False
            )

        db.session.add(
            User(
                username=request.form["username"],
                password=generate_password_hash(request.form["password"])
            )
        )
        db.session.commit()

        return render_template(
            "register.html",
            message="Registration successful! Wait for admin approval.",
            success=True
        )

    return render_template("register.html")

# ================= LOGIN =================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"]).first()

        if user and check_password_hash(user.password, request.form["password"]):
            if user.status != "approved":
                return render_template(
                    "login.html",
                    error="Account not approved by admin"
                )

            session["user"] = user.username
            session["role"] = user.role

            return redirect("/admin" if user.role == "admin" else "/dashboard")

    return render_template("login.html")

# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")

    news = get_news(
        request.args.get("category", "general"),
        request.args.get("search")
    )

    return render_template(
        "index.html",
        news=news,
        real_count=sum(1 for n in news if n["result"] == "REAL"),
        fake_count=sum(1 for n in news if n["result"] == "FAKE")
    )

# ================= ADMIN =================
@app.route("/admin")
def admin():
    if session.get("role") != "admin":
        return "Access Denied"

    search = request.args.get("search")

    if search:
        users = User.query.filter(
            User.username.contains(search),
            User.role != "admin"
        ).all()
    else:
        users = User.query.filter(User.role != "admin").all()

    logs = AdminLog.query.order_by(AdminLog.id.desc()).limit(10).all()

    return render_template("admin.html", users=users, logs=logs)

# ================= ACTIONS =================
@app.route("/approve/<int:id>")
def approve(id):
    user = User.query.get(id)
    user.status = "approved"
    db.session.add(AdminLog(action="Approved user", username=user.username))
    db.session.commit()
    return redirect("/admin")

@app.route("/reject/<int:id>")
def reject(id):
    user = User.query.get(id)
    user.status = "rejected"
    db.session.add(AdminLog(action="Rejected user", username=user.username))
    db.session.commit()
    return redirect("/admin")

@app.route("/delete/<int:id>")
def delete(id):
    user = User.query.get(id)
    db.session.add(AdminLog(action="Deleted user", username=user.username))
    db.session.delete(user)
    db.session.commit()
    return redirect("/admin")

# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ================= RUN APP =================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        # Create default admin
        if not User.query.filter_by(username="admin").first():
            db.session.add(
                User(
                    username="admin",
                    password=generate_password_hash("admin123"),
                    role="admin",
                    status="approved"
                )
            )
            db.session.commit()

    Timer(1, open_browser).start()
    print("🚀 Server starting...")
    app.run(app.run(host="0.0.0.0", port=5000)
)

