import matplotlib
matplotlib.use('Agg')  # Set the backend to Agg for non-GUI operation
import os
import json
import matplotlib.pyplot as plt
import numpy as np
from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime, timedelta
from flask import render_template_string
import yfinance as yf

app = Flask(__name__)

data_file = 'game_data.json'
history_file = 'game_history.json'
os.makedirs('static/graphs', exist_ok=True)

def load_data():
    if os.path.exists(data_file):
        with open(data_file, 'r') as f:
            return json.load(f)
    return {
        "players": [],
        "draft_order": [],
        "picks": {},
        "status": "setup",
        "all_picks": [],
        "time_frame": None,
        "start_date": None,
        "end_date": None,
        "trades": [],
        "milestones": [],
        "trade_limits": {}
    }

def save_data(data):
    with open(data_file, 'w') as f:
        json.dump(data, f, indent=2)

def load_history():
    if os.path.exists(history_file):
        with open(history_file, 'r') as f:
            return json.load(f)
    return []

def save_history(history):
    with open(history_file, 'w') as f:
        json.dump(history, f, indent=2)

def plot_stock(ticker, period='1mo', size=(4, 2)):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)
        if hist.empty:
            return None
        plt.figure(figsize=size)
        hist['Close'].plot(title=f"{ticker} - {period}")
        filename = f'static/graphs/{ticker}_{period}.png'
        plt.tight_layout()
        plt.savefig(filename)
        plt.close()
        return '/' + filename
    except Exception:
        return None

def plot_portfolio(player, picks, start_date, end_date, size=(6, 3)):
    try:
        start = datetime.fromisoformat(start_date).strftime('%Y-%m-%d')
        end = min(datetime.now(), datetime.fromisoformat(end_date)).strftime('%Y-%m-%d')
        plt.figure(figsize=size)
        dates = []
        values = []
        for date in np.arange(np.datetime64(start), np.datetime64(end), np.timedelta64(1, 'D')):
            date = date.astype('datetime64[D]').astype(datetime)
            total_value = 0
            for pick in picks:
                try:
                    hist = yf.Ticker(pick['ticker']).history(start=date, end=date + timedelta(days=1))
                    if not hist.empty:
                        total_value += hist['Close'].iloc[-1]
                except Exception:
                    continue
            if total_value > 0:
                dates.append(date)
                values.append(total_value)
        if dates and values:
            plt.plot(dates, values, label=f"{player}'s Portfolio")
            plt.title(f"{player}'s Portfolio Value")
            plt.xlabel("Date")
            plt.ylabel("Total Value ($)")
            plt.legend()
            plt.grid(True)
            filename = f'static/graphs/portfolio_{player}.png'
            plt.tight_layout()
            plt.savefig(filename)
            plt.close()
            return '/' + filename
        return None
    except Exception:
        return None

def get_snake_order(players, total_rounds):
    order = []
    for i in range(total_rounds):
        if i % 2 == 0:
            order.extend(players)
        else:
            order.extend(reversed(players))
    return order

def calculate_points(picks):
    if not picks:
        return 0
    total_change = 0
    count = 0
    for pick in picks:
        try:
            current = yf.Ticker(pick['ticker']).info.get('currentPrice')
            if current:
                change = ((current - pick['price']) / pick['price']) * 100
                total_change += change
                count += 1
        except Exception:
            continue
    return round(total_change / count, 2) if count > 0 else 0

def calculate_volatility(picks, start_date, end_date):
    try:
        start = datetime.fromisoformat(start_date).strftime('%Y-%m-%d')
        end = min(datetime.now(), datetime.fromisoformat(end_date)).strftime('%Y-%m-%d')
        volatilities = []
        for pick in picks:
            try:
                hist = yf.Ticker(pick['ticker']).history(start=start, end=end)
                if not hist.empty:
                    returns = hist['Close'].pct_change().dropna()
                    volatility = returns.std() * np.sqrt(252)  # Annualized volatility
                    volatilities.append(volatility)
            except Exception:
                continue
        return np.mean(volatilities) if volatilities else float('inf')
    except Exception:
        return float('inf')

def get_time_frame_dates(time_frame, start_date, custom_days=None):
    start = datetime.fromisoformat(start_date)
    if time_frame == "1 Quarter":
        return start + timedelta(days=90)
    elif time_frame == "6 Months":
        return start + timedelta(days=180)
    elif time_frame == "Fiscal Year":
        year = start.year
        if start.month > 6 or (start.month == 6 and start.day > 30):
            year += 1
        return datetime(year, 6, 30)
    elif time_frame == "Calendar Year":
        end_date = start + timedelta(days=365)
        if start.month <= 2 and end_date.month >= 3 and end_date.year % 4 == 0 and (end_date.year % 100 != 0 or end_date.year % 400 == 0):
            end_date += timedelta(days=1)
        return end_date
    elif time_frame == "Custom" and custom_days:
        return start + timedelta(days=custom_days)
    return start

def archive_game(data):
    history = load_history()
    leaderboard = []
    for player, picks in data['picks'].items():
        points = calculate_points(picks)
        leaderboard.append({'name': player, 'points': points})
    leaderboard.sort(key=lambda x: x['points'], reverse=True)
    game_record = {
        'id': len(history) + 1,
        'end_date': data['end_date'][:10],
        'time_frame': data['time_frame'],
        'winner': leaderboard[0]['name'] if leaderboard else None,
        'leaderboard': leaderboard,
        'picks': data['picks']
    }
    history.append(game_record)
    save_history(history)

@app.route('/')
def index():
    data = load_data()
    if data['status'] == 'draft':
        return redirect(url_for('draft'))
    return render_template_string('''
        <h1>Fantasy Stocks</h1>
        <form action="/names" method="post">
            Number of Players (2-12): <input type="number" name="num_players" min="2" max="12" required><br><br>
            Picks per Player: 
            <select name="num_picks">
                <option value="1">1</option>
                <option value="5">5</option>
                <option value="10">10</option>
            </select><br><br>
            Time Frame:
            <select name="time_frame" onchange="if(this.value=='Custom'){document.getElementById('custom_days').style.display='block';}else{document.getElementById('custom_days').style.display='none';}">
                <option value="1 Quarter">1 Quarter</option>
                <option value="6 Months">6 Months</option>
                <option value="Fiscal Year">Fiscal Year</option>
                <option value="Calendar Year">Calendar Year</option>
                <option value="Custom">Custom</option>
            </select><br>
            <div id="custom_days" style="display:none;">
                Custom Days (30-730): <input type="number" name="custom_days" min="30" max="730"><br>
            </div><br>
            <button type="submit">Next: Enter Player Names</button>
        </form>
        {% if players %}
            <p>Resume ongoing game:</p>
            <a href="/draft">Continue Draft</a><br>
            <a href="/game">View Game</a><br>
            <a href="/history">View Past Games</a>
        {% endif %}
    ''', players=data['players'])

@app.route('/names', methods=['POST'])
def names():
    try:
        num_players = int(request.form.get('num_players'))
        num_picks = request.form.get('num_picks')
        time_frame = request.form.get('time_frame')
        custom_days = request.form.get('custom_days')
    except (ValueError, TypeError):
        return redirect(url_for('index'))

    if num_players < 2 or num_players > 12:
        return redirect(url_for('index'))
    if num_picks not in ['1', '5', '10']:
        num_picks = '5'
    if time_frame not in ["1 Quarter", "6 Months", "Fiscal Year", "Calendar Year", "Custom"]:
        time_frame = "1 Quarter"
    if time_frame == "Custom":
        try:
            custom_days = int(custom_days)
            if custom_days < 30 or custom_days > 730:
                return redirect(url_for('index'))
        except (ValueError, TypeError):
            return redirect(url_for('index'))
    else:
        custom_days = None

    return render_template_string('''
        <h1>Fantasy Stocks - Enter Player Names</h1>
        <form action="/start" method="post">
            <input type="hidden" name="num_players" value="{{ num_players }}">
            <input type="hidden" name="num_picks" value="{{ num_picks }}">
            <input type="hidden" name="time_frame" value="{{ time_frame }}">
            {% if custom_days %}
                <input type="hidden" name="custom_days" value="{{ custom_days }}">
            {% endif %}
            {% for i in range(num_players) %}
                Player {{ i + 1 }} Name: <input name="player{{ i + 1 }}" required><br>
            {% endfor %}
            <button type="submit">Start Draft</button>
        </form>
        <a href="/">Back</a>
    ''', num_players=num_players, num_picks=num_picks, time_frame=time_frame, custom_days=custom_days)

@app.route('/start', methods=['POST'])
def start():
    try:
        num_players = int(request.form.get('num_players'))
        num_picks = request.form.get('num_picks')
        time_frame = request.form.get('time_frame')
        custom_days = request.form.get('custom_days')
        if custom_days:
            custom_days = int(custom_days)
    except (ValueError, TypeError):
        return redirect(url_for('index'))

    if num_players < 2 or num_players > 12:
        return redirect(url_for('index'))
    if num_picks not in ['1', '5', '10']:
        num_picks = '5'
    if time_frame not in ["1 Quarter", "6 Months", "Fiscal Year", "Calendar Year", "Custom"]:
        time_frame = "1 Quarter"
    if time_frame == "Custom" and (custom_days < 30 or custom_days > 730):
        return redirect(url_for('index'))

    players = []
    player_names = set()
    for i in range(1, num_players + 1):
        name = request.form.get(f'player{i}').strip()
        if not name:
            return render_template_string('''
                <h1>Error</h1>
                <p style="color: red;">All player names must be non-empty!</p>
                <a href="/">Back to Start</a>
            ''')
        if name in player_names:
            return render_template_string('''
                <h1>Error</h1>
                <p style="color: red;">Player names must be unique!</p>
                <a href="/">Back to Start</a>
            ''')
        player_names.add(name)
        players.append({'name': name, 'max': int(num_picks), 'picked': []})

    start_date = datetime.now().isoformat()
    end_date = get_time_frame_dates(time_frame, start_date, custom_days).isoformat()

    # Set up milestones at 1/3 and 2/3 of duration
    start_dt = datetime.fromisoformat(start_date)
    end_dt = datetime.fromisoformat(end_date)
    duration = (end_dt - start_dt).days
    milestone1 = (start_dt + timedelta(days=duration // 3)).isoformat()
    milestone2 = (start_dt + timedelta(days=2 * duration // 3)).isoformat()
    milestones = [
        {'time': milestone1, 'type': 'highest_gain', 'winner': None, 'value': 0},
        {'time': milestone2, 'type': 'lowest_volatility', 'winner': None, 'value': float('inf')}
    ]

    # Initialize trade limits
    trade_limits = {p['name']: 3 for p in players}

    player_names = [p['name'] for p in players]
    draft_order = get_snake_order(player_names, int(num_picks))
    
    data = {
        "players": players,
        "draft_order": draft_order,
        "picks": {},
        "status": "draft",
        "all_picks": [],
        "time_frame": time_frame,
        "start_date": start_date,
        "end_date": end_date,
        "trades": [],
        "milestones": milestones,
        "trade_limits": trade_limits
    }
    save_data(data)
    return redirect(url_for('draft'))

@app.route('/draft', methods=['GET', 'POST'])
def draft():
    data = load_data()
    if request.method == 'POST':
        name = request.form['name']
        ticker = request.form['ticker'].upper().strip()
        
        if not ticker:
            error = "Error: Please enter a stock ticker!"
            current_player = data['draft_order'][0]
            return render_template_string('''
                <h2>{{ player }}'s turn</h2>
                <p style="color: red;">{{ error }}</p>
                <form method="post">
                    <input name="name" type="hidden" value="{{ player }}">
                    Ticker Symbol: <input name="ticker">
                    <button type="submit">Pick</button>
                </form>
                <form method="get">
                    Preview ticker: <input name="preview">
                    <button type="submit">Preview</button>
                </form>
            ''', player=current_player, error=error)
        
        if ticker in data['all_picks']:
            error = f"Error: {ticker} has already been drafted!"
            current_player = data['draft_order'][0]
            return render_template_string('''
                <h2>{{ player }}'s turn</h2>
                <p style="color: red;">{{ error }}</p>
                <form method="post">
                    <input name="name" type="hidden" value="{{ player }}">
                    Ticker Symbol: <input name="ticker">
                    <button type="submit">Pick</button>
                </form>
                <form method="get">
                    Preview ticker: <input name="preview">
                    <button type="submit">Preview</button>
                </form>
            ''', player=current_player, error=error)
        
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            current = info.get('currentPrice') or info.get('regularMarketPrice')
            if not current:
                error = f"Error: {ticker} is not a valid stock ticker!"
                current_player = data['draft_order'][0]
                return render_template_string('''
                    <h2>{{ player }}'s turn</h2>
                    <p style="color: red;">{{ error }}</p>
                    <form method="post">
                        <input name="name" type="hidden" value="{{ player }}">
                        Ticker Symbol: <input name="ticker">
                        <button type="submit">Pick</button>
                    </form>
                    <form method="get">
                        Preview ticker: <input name="preview">
                        <button type="submit">Preview</button>
                    </form>
                ''', player=current_player, error=error)
        except Exception:
            error = f"Error: {ticker} is not a valid stock ticker!"
            current_player = data['draft_order'][0]
            return render_template_string('''
                <h2>{{ player }}'s turn</h2>
                <p style="color: red;">{{ error }}</p>
                <form method="post">
                    <input name="name" type="hidden" value="{{ player }}">
                    Ticker Symbol: <input name="ticker">
                    <button type="submit">Pick</button>
                </form>
                <form method="get">
                    Preview ticker: <input name="preview">
                    <button type="submit">Preview</button>
                </form>
            ''', player=current_player, error=error)
        
        data['picks'].setdefault(name, []).append({'ticker': ticker, 'price': current, 'time': datetime.now().isoformat()})
        data['all_picks'].append(ticker)
        for p in data['players']:
            if p['name'] == name:
                p['picked'].append(ticker)
        data['draft_order'].remove(name)
        save_data(data)
        return redirect(url_for('draft'))

    if not data['draft_order']:
        data['status'] = 'done'
        save_data(data)
        return '<h1>Draft Complete!</h1><a href="/">Home</a> | <a href="/game">View Game</a>'

    current_player = data['draft_order'][0]
    ticker = request.args.get('preview')
    graph_path = None
    stock_price = None
    preview_error = None
    if ticker:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            stock_price = info.get('currentPrice') or info.get('regularMarketPrice')
            graph_path = plot_stock(ticker)
            if not graph_path or not stock_price:
                preview_error = f"Unable to preview {ticker}: Invalid or unavailable stock data"
        except Exception:
            preview_error = f"Unable to preview {ticker}: Invalid stock ticker"

    return render_template_string('''
        <h2>{{ player }}'s turn</h2>
        <form method="post">
            <input name="name" type="hidden" value="{{ player }}">
            Ticker Symbol: <input name="ticker">
            <button type="submit">Pick</button>
        </form>
        {% if preview_error %}
            <p style="color: red;">{{ preview_error }}</p>
        {% elif graph %}
            <h3>Preview for {{ ticker }}: ${{ price }}</h3>
            <img src="{{ graph }}" style="max-width:300px">
        {% endif %}
        <form method="get">
            Preview ticker: <input name="preview">
            <button type="submit">Preview</button>
        </form>
    ''', player=current_player, ticker=ticker, graph=graph_path, price=stock_price, preview_error=preview_error)

@app.route('/trade', methods=['GET', 'POST'])
def trade():
    data = load_data()
    if data['status'] != 'done':
        return redirect(url_for('game'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'propose':
            from_player = request.form.get('from_player')
            to_player = request.form.get('to_player')
            offer_ticker = request.form.get('offer_ticker')
            request_ticker = request.form.get('request_ticker')
            
            if from_player == to_player or data['trade_limits'].get(from_player, 0) <= 0:
                return render_template_string('''
                    <h1>Trade Error</h1>
                    <p style="color: red;">Invalid trade or trade limit reached!</p>
                    <a href="/trade">Back to Trade</a> | <a href="/game">Back to Game</a>
                ''')
            
            trade_id = len(data['trades']) + 1
            data['trades'].append({
                'id': trade_id,
                'from_player': from_player,
                'to_player': to_player,
                'offer_ticker': offer_ticker,
                'request_ticker': request_ticker,
                'status': 'pending'
            })
            data['trade_limits'][from_player] -= 1
            save_data(data)
            return redirect(url_for('trade'))
        
        elif action == 'respond':
            trade_id = int(request.form.get('trade_id'))
            response = request.form.get('response')
            trade = next((t for t in data['trades'] if t['id'] == trade_id), None)
            if trade:
                trade['status'] = response
                if response == 'accepted':
                    from_picks = data['picks'][trade['from_player']]
                    to_picks = data['picks'][trade['to_player']]
                    from_pick = next(p for p in from_picks if p['ticker'] == trade['offer_ticker'])
                    to_pick = next(p for p in to_picks if p['ticker'] == trade['request_ticker'])
                    from_picks.remove(from_pick)
                    to_picks.remove(to_pick)
                    from_picks.append(to_pick)
                    to_picks.append(from_pick)
                    for p in data['players']:
                        if p['name'] == trade['from_player']:
                            p['picked'].remove(trade['offer_ticker'])
                            p['picked'].append(trade['request_ticker'])
                        elif p['name'] == trade['to_player']:
                            p['picked'].remove(trade['request_ticker'])
                            p['picked'].append(trade['offer_ticker'])
                save_data(data)
            return redirect(url_for('trade'))

    players = [p['name'] for p in data['players']]
    pending_trades = [t for t in data['trades'] if t['status'] == 'pending']
    return render_template_string('''
        <h1>Trade Stocks</h1>
        <h2>Propose Trade</h2>
        <form method="post">
            <input type="hidden" name="action" value="propose">
            From Player: <select name="from_player">
                {% for player in players %}
                    <option value="{{ player }}">{{ player }} ({{ trade_limits[player] }} trades left)</option>
                {% endfor %}
            </select><br>
            Offer Stock: <select name="offer_ticker">
                {% for player in players %}
                    {% for pick in picks[player] %}
                        <option value="{{ pick.ticker }}">{{ pick.ticker }} ({{ player }})</option>
                    {% endfor %}
                {% endfor %}
            </select><br>
            To Player: <select name="to_player">
                {% for player in players %}
                    <option value="{{ player }}">{{ player }}</option>
                {% endfor %}
            </select><br>
            Request Stock: <select name="request_ticker">
                {% for player in players %}
                    {% for pick in picks[player] %}
                        <option value="{{ pick.ticker }}">{{ pick.ticker }} ({{ player }})</option>
                    {% endfor %}
                {% endfor %}
            </select><br>
            <button type="submit">Propose Trade</button>
        </form>
        <h2>Pending Trades</h2>
        {% if pending_trades %}
            {% for trade in pending_trades %}
                <p>{{ trade.from_player }} offers {{ trade.offer_ticker }} to {{ trade.to_player }} for {{ trade.request_ticker }}</p>
                {% if trade.to_player in players %}
                    <form method="post">
                        <input type="hidden" name="action" value="respond">
                        <input type="hidden" name="trade_id" value="{{ trade.id }}">
                        <button type="submit" name="response" value="accepted">Accept</button>
                        <button type="submit" name="response" value="rejected">Reject</button>
                    </form>
                {% endif %}
            {% endfor %}
        {% else %}
            <p>No pending trades.</p>
        {% endif %}
        <a href="/game">Back to Game</a>
    ''', players=players, picks=data['picks'], pending_trades=pending_trades, trade_limits=data['trade_limits'])

@app.route('/game')
def game():
    data = load_data()
    summaries = {}
    leaderboard = []
    game_ended = False
    winner = None
    milestone_results = []

    if data['end_date']:
        end_date = datetime.fromisoformat(data['end_date'])
        if datetime.now() > end_date:
            data['status'] = 'finished'
            game_ended = True
            save_data(data)

    # Process milestones
    now = datetime.now()
    for milestone in data['milestones']:
        milestone_time = datetime.fromisoformat(milestone['time'])
        if now >= milestone_time and not milestone['winner']:
            if milestone['type'] == 'highest_gain':
                max_gain = -float('inf')
                winner = None
                for player, picks in data['picks'].items():
                    for pick in picks:
                        try:
                            current = yf.Ticker(pick['ticker']).info.get('currentPrice')
                            if current:
                                gain = ((current - pick['price']) / pick['price']) * 100
                                if gain > max_gain:
                                    max_gain = gain
                                    winner = player
                        except Exception:
                            continue
                milestone['winner'] = winner
                milestone['value'] = round(max_gain, 2)
            elif milestone['type'] == 'lowest_volatility':
                min_volatility = float('inf')
                winner = None
                for player, picks in data['picks'].items():
                    volatility = calculate_volatility(picks, data['start_date'], data['end_date'])
                    if volatility < min_volatility:
                        min_volatility = volatility
                        winner = player
                milestone['winner'] = winner
                milestone['value'] = round(min_volatility, 2)
            save_data(data)
        milestone_results.append(milestone)

    for player, picks in data['picks'].items():
        summaries[player] = []
        points = calculate_points(picks)
        # Add milestone bonuses
        bonus = sum(5 for m in milestone_results if m['winner'] == player)  # +5% per milestone win
        points += bonus
        leaderboard.append({'name': player, 'points': points, 'bonus': bonus})
        portfolio_graph = plot_portfolio(player, picks, data['start_date'], data['end_date'])
        for pick in picks:
            try:
                current = yf.Ticker(pick['ticker']).info.get('currentPrice')
                change = ((current - pick['price']) / pick['price']) * 100 if current else 0
            except Exception:
                current = None
                change = 0
            graph_path = plot_stock(pick['ticker'])
            summaries[player].append({
                'ticker': pick['ticker'],
                'draft_price': pick['price'],
                'current_price': current,
                'change': round(change, 2),
                'graph': graph_path
            })

    leaderboard.sort(key=lambda x: x['points'], reverse=True)
    if game_ended and leaderboard:
        winner = leaderboard[0]['name']

    trade_history = [t for t in data['trades'] if t['status'] != 'pending']
    return render_template_string('''
        <h1>Game Summary</h1>
        <p>Time Frame: {{ time_frame }}</p>
        <p>Start Date: {{ start_date }}</p>
        <p>End Date: {{ end_date }}</p>
        {% if game_ended %}
            <h2>Game Over! Winner: {{ winner }}</h2>
            <form action="/new_game" method="post">
                <button type="submit">Start New Game</button>
            </form>
        {% else %}
            <p>Game Status: {{ 'Ongoing' if status == 'done' else status }}</p>
            <a href="/trade">Trade Stocks</a>
        {% endif %}
        <h2>Leaderboard</h2>
        <table border="1">
            <tr><th>Player</th><th>Points (% Change)</th><th>Bonus Points</th></tr>
            {% for entry in leaderboard %}
                <tr><td>{{ entry.name }}</td><td>{{ entry.points }}</td><td>{{ entry.bonus }}</td></tr>
            {% endfor %}
        </table>
        <h2>Milestones</h2>
        {% for milestone in milestone_results %}
            <p>{{ milestone.time[:10] }} - {{ milestone.type.replace('_', ' ').title() }}: 
            {% if milestone.winner %}
                {{ milestone.winner }} ({{ milestone.value }})
            {% else %}
                Pending
            {% endif %}
            </p>
        {% endfor %}
        <h2>Trade History</h2>
        {% if trade_history %}
            {% for trade in trade_history %}
                <p>{{ trade.from_player }} traded {{ trade.offer_ticker }} for {{ trade.to_player }}'s {{ trade.request_ticker }} ({{ trade.status }})</p>
            {% endfor %}
        {% else %}
            <p>No trades completed.</p>
        {% endif %}
        {% for player, picks in summaries.items() %}
            <h2>{{ player }} (Points: {{ leaderboard[loop.index0].points }})</h2>
            {% if summaries[player][0].portfolio_graph %}
                <h3>Portfolio Performance</h3>
                <img src="{{ summaries[player][0].portfolio_graph }}" style="max-width:600px">
            {% endif %}
            <ul>
            {% for stock in picks %}
                <li>
                    <a href="/stock/{{ stock.ticker }}">{{ stock.ticker }}</a> - Draft: ${{ stock.draft_price }} | Now: ${{ stock.current_price or 'N/A' }} ({{ stock.change }}%)<br>
                    {% if stock.graph %}<a href="/stock/{{ stock.ticker }}"><img src="{{ stock.graph }}" style="max-height: 60px"></a>{% else %}<span>No graph available</span>{% endif %}
                </li>
            {% endfor %}
            </ul>
        {% endfor %}
        <a href="/">Home</a> | <a href="/history">View Past Games</a>
    ''', 
    summaries=summaries, 
    leaderboard=leaderboard, 
    time_frame=data['time_frame'], 
    start_date=data['start_date'][:10] if data['start_date'] else 'N/A', 
    end_date=data['end_date'][:10] if data['end_date'] else 'N/A', 
    status=data['status'],
    game_ended=game_ended,
    winner=winner,
    milestone_results=milestone_results,
    trade_history=trade_history)

@app.route('/new_game', methods=['POST'])
def new_game():
    data = load_data()
    if data['status'] == 'finished':
        archive_game(data)
    data = {
        "players": [],
        "draft_order": [],
        "picks": {},
        "status": "setup",
        "all_picks": [],
        "time_frame": None,
        "start_date": None,
        "end_date": None,
        "trades": [],
        "milestones": [],
        "trade_limits": {}
    }
    save_data(data)
    return redirect(url_for('index'))

@app.route('/history')
def history():
    history = load_history()
    return render_template_string('''
        <h1>Past Games</h1>
        {% if history %}
            {% for game in history %}
                <h2>Game {{ game.id }} - Ended {{ game.end_date }} ({{ game.time_frame }})</h2>
                <p>Winner: {{ game.winner }}</p>
                <h3>Leaderboard</h3>
                <table border="1">
                    <tr><th>Player</th><th>Points (% Change)</th></tr>
                    {% for entry in game.leaderboard %}
                        <tr><td>{{ entry.name }}</td><td>{{ entry.points }}</td></tr>
                    {% endfor %}
                </table>
                <h3>Picks</h3>
                {% for player, picks in game.picks.items() %}
                    <p>{{ player }}: {{ picks|map(attribute='ticker')|join(', ') }}</p>
                {% endfor %}
            {% endfor %}
        {% else %}
            <p>No past games found.</p>
        {% endif %}
        <a href="/">Home</a> | <a href="/game">Back to Game</a>
    ''', history=history)

@app.route('/stock/<ticker>')
def stock_detail(ticker):
    periods = ['1d', '5d', '1mo', '6mo', 'ytd', '1y', '5y', 'max']
    selected = request.args.get('period', '1mo')
    graph_path = plot_stock(ticker, selected, size=(6, 3))
    return render_template_string('''
        <h1>{{ ticker }} Performance</h1>
        <form method="get">
            <input type="hidden" name="ticker" value="{{ ticker }}">
            Period:
            <select name="period" onchange="this.form.submit()">
                {% for p in periods %}<option value="{{ p }}" {% if p == selected %}selected{% endif %}>{{ p }}</option>{% endfor %}
            </select>
        </form>
        {% if graph %}<img src="{{ graph }}" style="max-width: 600px">{% else %}<p>No graph available</p>{% endif %}
        <br><a href="/game">Back to Game</a>
    ''', ticker=ticker, periods=periods, selected=selected, graph=graph_path)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
