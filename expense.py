from flask import Flask, request, redirect, url_for, render_template_string, send_file
import sqlite3
import csv
import io
from datetime import datetime

app = Flask(__name__)
DB_NAME = "expenses.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Create table if it does not exist
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            tx_type TEXT NOT NULL CHECK(tx_type IN ('Income', 'Expense')),
            tx_date TEXT NOT NULL
        )
        """
    )

    # Check existing columns to avoid crashes from old database schema
    cursor.execute("PRAGMA table_info(transactions)")
    columns = [row[1] for row in cursor.fetchall()]

    # If old schema exists (type/date), rebuild table safely
    if "tx_type" not in columns or "tx_date" not in columns:
        cursor.execute("DROP TABLE IF EXISTS transactions")
        cursor.execute(
            """
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                tx_type TEXT NOT NULL CHECK(tx_type IN ('Income', 'Expense')),
                tx_date TEXT NOT NULL
            )
            """
        )

    conn.commit()
    conn.close()


# Make sure database is created even when running with `flask run`
init_db()


@app.route("/", methods=["GET"])
def index():
    conn = get_connection()

    selected_type = request.args.get("type", "")
    selected_category = request.args.get("category", "")

    query = "SELECT * FROM transactions WHERE 1=1"
    params = []

    if selected_type:
        query += " AND tx_type = ?"
        params.append(selected_type)

    if selected_category:
        query += " AND category = ?"
        params.append(selected_category)

    query += " ORDER BY tx_date DESC, id DESC"
    transactions = conn.execute(query, params).fetchall()

    summary = conn.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN tx_type='Income' THEN amount END), 0) AS total_income,
            COALESCE(SUM(CASE WHEN tx_type='Expense' THEN amount END), 0) AS total_expense
        FROM transactions
        """
    ).fetchone()

    category_data = conn.execute(
        """
        SELECT category, COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE tx_type='Expense'
        GROUP BY category
        ORDER BY total DESC
        """
    ).fetchall()

    categories = conn.execute(
        "SELECT DISTINCT category FROM transactions ORDER BY category"
    ).fetchall()

    conn.close()

    balance = float(summary["total_income"] or 0) - float(summary["total_expense"] or 0)

    return render_template_string(
        TEMPLATE,
        transactions=transactions,
        total_income=float(summary["total_income"] or 0),
        total_expense=float(summary["total_expense"] or 0),
        balance=balance,
        category_data=category_data,
        categories=categories,
        selected_type=selected_type,
        selected_category=selected_category,
        now=datetime.now().strftime("%Y-%m-%d")
    )


@app.route("/add", methods=["POST"])
def add_transaction():
    title = request.form.get("title", "").strip()
    amount = request.form.get("amount", "").strip()
    category = request.form.get("category", "").strip()
    tx_type = request.form.get("type", "").strip()
    tx_date = request.form.get("date", "").strip()

    if not title or not amount or not category or tx_type not in ["Income", "Expense"] or not tx_date:
        return redirect(url_for("index"))

    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError
    except ValueError:
        return redirect(url_for("index"))

    conn = get_connection()
    conn.execute(
        "INSERT INTO transactions (title, amount, category, tx_type, tx_date) VALUES (?, ?, ?, ?, ?)",
        (title, amount, category, tx_type, tx_date)
    )
    conn.commit()
    conn.close()

    return redirect(url_for("index"))


@app.route("/delete/<int:tx_id>")
def delete_transaction(tx_id):
    conn = get_connection()
    conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


@app.route("/export")
def export_csv():
    conn = get_connection()
    transactions = conn.execute("SELECT * FROM transactions ORDER BY tx_date DESC, id DESC").fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Title", "Amount", "Category", "Type", "Date"])

    for tx in transactions:
        writer.writerow([
            tx["id"],
            tx["title"],
            tx["amount"],
            tx["category"],
            tx["tx_type"],
            tx["tx_date"]
        ])

    mem = io.BytesIO()
    mem.write(output.getvalue().encode("utf-8"))
    mem.seek(0)
    output.close()

    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name="transactions.csv"
    )


TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Smart Expense Tracker</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: Arial, sans-serif; }
        body { background: #f4f7fb; color: #222; padding: 20px; }
        .container { max-width: 1200px; margin: auto; }
        h1 { margin-bottom: 20px; text-align: center; color: #1d3557; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; margin-bottom: 20px; }
        .card { background: white; padding: 18px; border-radius: 14px; box-shadow: 0 8px 20px rgba(0,0,0,0.08); }
        .card h2 { font-size: 18px; margin-bottom: 10px; color: #1d3557; }
        .value { font-size: 28px; font-weight: bold; }
        .income { color: #1b8a3e; }
        .expense { color: #d62828; }
        .balance { color: #264653; }
        form { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
        input, select, button { padding: 10px; border-radius: 10px; border: 1px solid #ccc; font-size: 14px; }
        button { background: #1d3557; color: white; border: none; cursor: pointer; }
        button:hover { background: #16324f; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; background: white; border-radius: 14px; overflow: hidden; box-shadow: 0 8px 20px rgba(0,0,0,0.08); }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; }
        th { background: #1d3557; color: white; }
        tr:hover { background: #f8fbff; }
        .actions a { color: #d62828; text-decoration: none; font-weight: bold; }
        .chart-list { list-style: none; margin-top: 10px; }
        .chart-list li { padding: 8px 0; border-bottom: 1px solid #eee; }
        .topbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 10px; }
        .export-link { text-decoration: none; background: #2a9d8f; color: white; padding: 10px 14px; border-radius: 10px; }
        .muted { color: #666; font-size: 13px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="topbar">
            <h1>Smart Expense Tracker</h1>
            <a class="export-link" href="/export">Export CSV</a>
        </div>

        <div class="grid">
            <div class="card">
                <h2>Total Income</h2>
                <div class="value income">₹ {{ "%.2f" % total_income }}</div>
            </div>
            <div class="card">
                <h2>Total Expense</h2>
                <div class="value expense">₹ {{ "%.2f" % total_expense }}</div>
            </div>
            <div class="card">
                <h2>Balance</h2>
                <div class="value balance">₹ {{ "%.2f" % balance }}</div>
            </div>
        </div>

        <div class="card" style="margin-bottom: 20px;">
            <h2>Add Transaction</h2>
            <br>
            <form method="POST" action="/add">
                <input type="text" name="title" placeholder="Title" required>
                <input type="number" step="0.01" name="amount" placeholder="Amount" required>
                <input type="text" name="category" placeholder="Category (Food, Salary, Travel...)" required>
                <select name="type" required>
                    <option value="">Select Type</option>
                    <option value="Income">Income</option>
                    <option value="Expense">Expense</option>
                </select>
                <input type="date" name="date" value="{{ now }}" required>
                <button type="submit">Add</button>
            </form>
        </div>

        <div class="card" style="margin-bottom: 20px;">
            <h2>Filter Transactions</h2>
            <br>
            <form method="GET" action="/">
                <select name="type">
                    <option value="">All Types</option>
                    <option value="Income" {% if selected_type == 'Income' %}selected{% endif %}>Income</option>
                    <option value="Expense" {% if selected_type == 'Expense' %}selected{% endif %}>Expense</option>
                </select>
                <select name="category">
                    <option value="">All Categories</option>
                    {% for category in categories %}
                        <option value="{{ category['category'] }}" {% if selected_category == category['category'] %}selected{% endif %}>{{ category['category'] }}</option>
                    {% endfor %}
                </select>
                <button type="submit">Apply Filter</button>
            </form>
        </div>

        <div class="grid">
            <div class="card">
                <h2>Expense by Category</h2>
                {% if category_data %}
                    <ul class="chart-list">
                        {% for item in category_data %}
                            <li><strong>{{ item['category'] }}</strong>: ₹ {{ "%.2f" % item['total'] }}</li>
                        {% endfor %}
                    </ul>
                {% else %}
                    <p class="muted">No expense data yet.</p>
                {% endif %}
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Title</th>
                    <th>Amount</th>
                    <th>Category</th>
                    <th>Type</th>
                    <th>Date</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody>
                {% if transactions %}
                    {% for tx in transactions %}
                        <tr>
                            <td>{{ tx['id'] }}</td>
                            <td>{{ tx['title'] }}</td>
                            <td>₹ {{ "%.2f" % tx['amount'] }}</td>
                            <td>{{ tx['category'] }}</td>
                            <td>{{ tx['tx_type'] }}</td>
                            <td>{{ tx['tx_date'] }}</td>
                            <td class="actions"><a href="/delete/{{ tx['id'] }}" onclick="return confirm('Delete this transaction?')">Delete</a></td>
                        </tr>
                    {% endfor %}
                {% else %}
                    <tr>
                        <td colspan="7">No transactions found.</td>
                    </tr>
                {% endif %}
            </tbody>
        </table>
    </div>
</body>
</html>
"""


if __name__ == "__main__":
    # Disable everything that uses multiprocessing (important for your environment)
    app.run(debug=False, use_reloader=False, use_debugger=False, threaded=False)
