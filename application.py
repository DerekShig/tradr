import os
import requests
from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
# if not os.environ.get("API_KEY"):
#     raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    user = session["user_id"]
    portfolio = db.execute("SELECT symbol, shares, name FROM portfolio WHERE user_id = (?)", user)
    current_cash = db.execute("SELECT cash FROM users WHERE id = (?)", user)
    current_cash = current_cash[0]['cash']

    # get list of stock prices in order in portfolio
    total = 0.00
    price = []
    for i in portfolio:
        stock = requests.get('https://cloud.iexapis.com/stable/stock/' + i["symbol"] + '/quote?token=pk_e3490e2bde5c48b7a65143b7fc70cfe5').json()["latestPrice"]
        price.append(stock)

    # number of shares in list
    share_num = db.execute("SELECT shares FROM portfolio WHERE user_id = (?)", user)

    # sum share price x num of shares for each stock in portfolio
    counter = 0
    for i in share_num:
        total = total + (int(i["shares"]) * float(price[counter]))
        counter += 1

    return render_template("index.html", portfolio=portfolio, price=price, current_cash=current_cash, total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "GET":
        return render_template("buy.html")

    else:
        symbol = request.form.get("symbol").lower()
        shares = request.form.get("shares")
        quote = requests.get('https://cloud.iexapis.com/stable/stock/'+symbol+'/quote?token=pk_e3490e2bde5c48b7a65143b7fc70cfe5')
        # if invalid ticker
        if quote.status_code == 500 or quote.status_code == 404:
            flash("Please enter a valid stock ticker.", "danger")
            return render_template("buy.html")
        name = quote.json()["companyName"]
        user = session["user_id"]
        current_cash = db.execute("SELECT cash FROM users WHERE id = (?)", user)
        current_cash = current_cash[0]['cash']
        new_balance = current_cash - (float(quote.json()["latestPrice"]) * int(shares))

        # count number of rows where stock and user_id match, to see if they have the stock or not
        portfolio = db.execute("SELECT COUNT(user_id) FROM portfolio WHERE user_id = (?) AND symbol = (?)", user, symbol)

        #if valid stock and user has enough funds
        if quote.status_code == 200 and ( new_balance >= 0 ):
            db.execute("INSERT INTO buy (user_id, stock, shares, price) VALUES (?, ?, ?, ?)", user, symbol, shares, quote.json()["latestPrice"])
            db.execute("UPDATE users SET cash = (?) WHERE id = (?)", new_balance, user)
            #if stock not in portfolio, add stock
            if portfolio[0]["COUNT(user_id)"] == 0:
                db.execute("INSERT INTO portfolio (user_id, symbol, shares, name) VALUES (?, ?, ?, ?)", user, symbol, shares, name)
                flash("Bought!", "primary")
                return redirect("/")
            # if stock already in portfolio, add to it
            else:
                db.execute("UPDATE portfolio SET shares = shares + (?) WHERE user_id = (?) AND symbol = (?)", shares, user, symbol)
                flash("Bought!", "primary")
                return redirect("/")
        # if not enough funds in account
        elif new_balance < 0:
            flash("You do not have enough funds in account.", "danger")
            return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user = session["user_id"]
    history = db.execute("SELECT stock, shares, price, time FROM buy where user_id = (?)", user)
    return render_template("history.html", history=history)


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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            flash("Username or password incorrect.", "danger")
            return render_template("login.html")

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

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    else:
        ticker = request.form.get("symbol")
        quote = requests.get('https://cloud.iexapis.com/stable/stock/'+ticker+'/quote?token=pk_e3490e2bde5c48b7a65143b7fc70cfe5')
        if quote.status_code == 200:
            return render_template("quoted.html", quote=quote.json()["latestPrice"], name=quote.json()["companyName"], exchange=quote.json()["primaryExchange"], opened=quote.json()["open"], closed=quote.json()["close"])
        else:
            flash("Please enter a valid stock ticker", "danger")
            return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))
    if request.method == "GET":
        return render_template("register.html")
    else:
        # if no username exists and passwords match
        if (request.form.get("password")) == (request.form.get("confirmation")) and len(rows) == 0:
            hashed = generate_password_hash(request.form.get("password"))
            username = request.form.get("username")
            db.execute("INSERT INTO users (username, hash, cash) VALUES (:username, :password, 10000)", username=username, password=hashed)
            flash("Account created!", "primary")
            return render_template("login.html")
        # if passwords do not match
        elif (request.form.get("password")) != (request.form.get("confirmation")) and len(rows) == 0:
            flash("Your passwords do not match.", "danger")
            return render_template("register.html")
        # if username exists
        else:
            flash("Username already exists.", "danger")
            return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        return render_template("sell.html")
    else:
        shares = request.form.get("shares")
        user = session["user_id"]
        symbol = request.form.get("symbol").lower()
        price = requests.get('https://cloud.iexapis.com/stable/stock/'+symbol+'/quote?token=pk_e3490e2bde5c48b7a65143b7fc70cfe5')

        # if invalid stock ticker
        if price.status_code != 200:
            flash("Please enter a valid stock ticker.", "danger")
            return render_template("sell.html")

        current_cash = db.execute("SELECT cash FROM users WHERE id = (?)", user)
        current_cash = current_cash[0]['cash']
        new_balance = current_cash + (float(price.json()["latestPrice"]) * int(shares))

        shares_owned = db.execute("SELECT shares FROM portfolio WHERE user_id = (?) AND symbol = (?)", user, symbol)

        # user does not own stock
        if shares_owned == []:
            flash("You do not own that stock.", "danger")
            return render_template("sell.html")

        # user tried to sell more shares than they own
        if int(shares_owned[0]["shares"]) < int(shares):
            flash("You do not own that many shares.", "danger")
            return render_template("sell.html")

        # if they sell all their stock
        if int(shares_owned[0]["shares"]) == int(shares):
            # update cash balance
            db.execute("UPDATE users SET cash = (?) WHERE id = (?)", new_balance, user)
            # update portfolio
            db.execute("DELETE FROM portfolio WHERE user_id = (?) AND symbol = (?)", user, symbol)
            # update history
            db.execute("INSERT INTO buy (user_id, stock, shares, price) VALUES (?, ?, ?, ?)", user, symbol, "-" + shares, price.json()["latestPrice"])
            flash("Sold!", "primary")
            return redirect("/")

        # if they sell less than all of their shares (from 1 - n shares)
        if int(shares_owned[0]["shares"]) > int(shares):
            # update cash balance
            db.execute("UPDATE users SET cash = (?) WHERE id = (?)", new_balance, user)
            # update portfolio
            db.execute("UPDATE portfolio SET shares = shares - (?) WHERE user_id = (?) AND symbol = (?)", shares, user, symbol)
            #update history
            db.execute("INSERT INTO buy (user_id, stock, shares, price) VALUES (?, ?, ?, ?)", user, symbol, "-" + shares, price.json()["latestPrice"])
            flash("Sold!", "primary")
            return redirect("/")

        return "error 500"


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
