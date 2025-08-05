import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd, get_user_portfolio, get_user_cash

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = session["user_id"]
    portfolio, total_portfolio_value = get_user_portfolio(user_id, db)
    cash = get_user_cash(user_id, db)
    total = total_portfolio_value + cash

    return render_template(
        "portfolio.html",
        portfolio=portfolio,
        cash=cash,
        total=total
    )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        if not symbol:
            return apology("missing symbol", 400)
        if not shares:
            return apology("missing shares", 400)
        if not shares.isdigit() or int(shares) < 0:
            return apology("only positive integers allowed", 400)

        shares = int(shares)
        quote_data = lookup(symbol)
        if quote_data:
            _, price, symbol = quote_data.values()

            # Available cash validation
            cash = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])[0]["cash"]
            total_cost = price * shares
            if total_cost > cash:
                return apology("can't afford", 400)

            # Update user's cash balance
            new_cash_balance = cash - total_cost
            db.execute("UPDATE users SET cash = ? WHERE id = ?",
                       new_cash_balance, session["user_id"])

            # Insert transcation into database
            db.execute(
                "INSERT INTO transactions (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)",
                session["user_id"], symbol, shares, price
            )

            flash(f"Successfully bought {shares} share(s) of {symbol} at ${price:.2f} each!")

            return redirect("/")

        else:
            return apology("ivalid symbol", 400)

    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    transactions = db.execute(
        "SELECT symbol, shares, price, timestamp FROM transactions WHERE user_id = ? ORDER BY timestamp DESC",
        session["user_id"]
    )

    for tx in transactions:
        tx["price"] = usd(tx["price"])

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""
    session.clear()

    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "POST":
        quote_data = lookup(request.form.get("symbol"))
        if quote_data:
            name, price, symbol = quote_data.values()
            return render_template(
                "quoted.html",
                name=name,
                price=usd(price),
                symbol=symbol
            )
        else:
            return apology("ivalid symbol", 400)

    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username:
            return apology("must provide username", 400)
        if not password:
            return apology("must provide password", 400)
        if password != request.form.get("confirmation"):
            return apology("passwords do not match", 400)

        try:
            id = db.execute(
                "INSERT INTO users (username, hash) VALUES(?, ?)",
                username,
                generate_password_hash(password)
            )
            session["user_id"] = id
            return redirect("/")

        except ValueError:
            return apology("username already taken", 400)

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_id = session["user_id"]
    portfolio, _ = get_user_portfolio(user_id, db)

    if request.method == "POST":
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("missing symbol", 400)

        quote_data = lookup(request.form.get("symbol"))
        if quote_data:
            cash = get_user_cash(user_id, db)
            shares_to_sell = int(request.form.get("shares"))
            shares = next((stock["shares"] for stock in portfolio if stock["symbol"] == symbol), 0)
            _, price, _ = quote_data.values()

            if shares_to_sell > shares:
                return apology("too many shares", 400)

            cash += shares_to_sell * price
            db.execute(
                "INSERT INTO transactions (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)",
                user_id, symbol, - shares_to_sell, price
            )
            db.execute("UPDATE users SET cash = ? WHERE id = ?",
                       cash, session["user_id"])

        else:
            return apology("missing symbol", 400)

        return redirect("/")

    return render_template("sell.html", portfolio=portfolio)
