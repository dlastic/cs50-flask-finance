import requests

from flask import redirect, render_template, session
from functools import wraps


def apology(message, code=400):
    """Render message as an apology to user."""

    def escape(s):
        """
        Escape special characters.

        https://github.com/jacebrowning/memegen#special-characters
        """
        for old, new in [
            ("-", "--"),
            (" ", "-"),
            ("_", "__"),
            ("?", "~q"),
            ("%", "~p"),
            ("#", "~h"),
            ("/", "~s"),
            ('"', "''"),
        ]:
            s = s.replace(old, new)
        return s

    return render_template("apology.html", top=code, bottom=escape(message)), code


def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/latest/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function


def lookup(symbol):
    """Look up quote for symbol."""
    url = f"https://finance.cs50.io/quote?symbol={symbol.upper()}"
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an error for HTTP error responses
        quote_data = response.json()
        return {
            "name": quote_data["companyName"],
            "price": quote_data["latestPrice"],
            "symbol": symbol.upper()
        }
    except requests.RequestException as e:
        print(f"Request error: {e}")
    except (KeyError, ValueError) as e:
        print(f"Data parsing error: {e}")
    return None


def usd(value):
    """Format value as USD."""
    return f"${value:,.2f}"


def get_user_portfolio(user_id, db):
    """Get the user's portfolio."""
    transactions = db.execute(
        """
        SELECT symbol,
            SUM(shares) AS total_shares
        FROM transactions
        WHERE user_id = ?
        GROUP BY symbol
        """,
        user_id
    )

    portfolio = []
    total_portfolio_value = 0

    for transaction in transactions:
        symbol = transaction["symbol"]
        total_shares = transaction["total_shares"]

        quote_data = lookup(symbol)
        if quote_data:
            price = quote_data["price"]
            total_value = price * total_shares
            total_portfolio_value += total_value

            portfolio.append({
                "symbol": symbol,
                "shares": total_shares,
                "price": price,
                "total_value": total_value
            })

    return portfolio, total_portfolio_value


def get_user_cash(user_id, db):
    """Get the user's available cash."""
    cash = db.execute(
        "SELECT cash FROM users WHERE id = ?", user_id
    )
    if cash:
        return cash[0]["cash"]
    else:
        return None
