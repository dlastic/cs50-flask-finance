from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import (
    apology,
    login_required,
    lookup,
    usd,
    get_user_portfolio,
    get_user_cash,
)

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

engine = create_engine("sqlite:///finance.db")


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
    portfolio, total_portfolio_value = get_user_portfolio(user_id, engine)
    cash = get_user_cash(user_id, engine)
    total = total_portfolio_value + cash

    return render_template(
        "portfolio.html", portfolio=portfolio, cash=cash, total=total
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
        if not shares.isdigit() or int(shares) <= 0:
            return apology("only positive integers allowed", 400)

        shares = int(shares)
        quote_data = lookup(symbol)
        if quote_data:
            _, price, symbol = quote_data.values()

            with engine.connect() as conn:
                # SELECT cash
                result = conn.execute(
                    text("SELECT cash FROM users WHERE id = :id"),
                    {"id": session["user_id"]},
                )
                row = result.mappings().first()
                if row is None:
                    return apology("user not found", 400)
                cash = row["cash"]

                # Check if user can afford
                total_cost = price * shares
                if total_cost > cash:
                    return apology("can't afford", 400)

                # UPDATE cash
                new_cash_balance = cash - total_cost
                conn.execute(
                    text("UPDATE users SET cash = :cash WHERE id = :id"),
                    {"cash": new_cash_balance, "id": session["user_id"]},
                )

                # INSERT transaction
                conn.execute(
                    text(
                        "INSERT INTO transactions (user_id, symbol, shares, price) VALUES (:user_id, :symbol, :shares, :price)"
                    ),
                    {
                        "user_id": session["user_id"],
                        "symbol": symbol,
                        "shares": shares,
                        "price": price,
                    },
                )

                # Commit changes
                conn.commit()

            flash(
                f"Successfully bought {shares} share(s) of {symbol} at ${price:.2f} each!"
            )

            return redirect("/")

        else:
            return apology("ivalid symbol", 400)

    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    with engine.connect() as conn:
        result = (
            conn.execute(
                text(
                    """
                SELECT symbol, shares, price, timestamp
                FROM transactions
                WHERE user_id = :user_id
                ORDER BY timestamp DESC
                """
                ),
                {"user_id": session["user_id"]},
            )
            .mappings()
            .all()
        )

    transactions = []
    for tx in result:
        tx_dict = dict(tx)
        tx_dict["price"] = usd(tx_dict["price"])
        transactions.append(tx_dict)

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    session.clear()

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username:
            return apology("must provide username", 403)
        if not password:
            return apology("must provide password", 403)

        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT * FROM users WHERE username = :username"),
                {"username": username},
            )
            row = result.mappings().first()

        if row is None or not check_password_hash(row["hash"], password):
            return apology("invalid username and/or password", 403)

        session["user_id"] = row["id"]

        return redirect("/")

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
                "quoted.html", name=name, price=usd(price), symbol=symbol
            )
        else:
            return apology("invalid symbol", 400)

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
            with engine.connect() as conn:
                password_hash = generate_password_hash(password)
                result = conn.execute(
                    text("INSERT INTO users (username, hash) VALUES(:username, :hash)"),
                    {"username": username, "hash": password_hash},
                )
                conn.commit()
                session["user_id"] = result.lastrowid
                return redirect("/")
        except IntegrityError:
            return apology("username already taken", 400)

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_id = session["user_id"]
    portfolio, _ = get_user_portfolio(user_id, engine)

    if request.method == "POST":
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("missing symbol", 400)

        quote_data = lookup(symbol)
        if quote_data:
            cash = get_user_cash(user_id, engine)
            shares_str = request.form.get("shares")
            if not shares_str or not shares_str.isdigit() or int(shares_str) <= 0:
                return apology("invalid number of shares", 400)
            shares_to_sell = int(shares_str)
            shares = next(
                (stock["shares"] for stock in portfolio if stock["symbol"] == symbol), 0
            )
            _, price, _ = quote_data.values()

            if shares_to_sell > shares:
                return apology("too many shares", 400)

            new_cash = cash + shares_to_sell * price

            with engine.connect() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO transactions (user_id, symbol, shares, price)
                        VALUES (:user_id, :symbol, :shares, :price)
                    """
                    ),
                    {
                        "user_id": user_id,
                        "symbol": symbol,
                        "shares": -shares_to_sell,
                        "price": price,
                    },
                )

                conn.execute(
                    text("UPDATE users SET cash = :cash WHERE id = :id"),
                    {"cash": new_cash, "id": user_id},
                )

                conn.commit()

        else:
            return apology("invalid symbol", 400)

        return redirect("/")

    return render_template("sell.html", portfolio=portfolio)
