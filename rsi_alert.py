# === FILE: rsi_alert.py ===
import requests
import pandas as pd
import numpy as np
import time
import os
from datetime import datetime
from telegram import Bot
import ta
import matplotlib.pyplot as plt
from io import BytesIO

# === DÁN BOT_TOKEN VÀ CHAT_ID VÀO ĐÂY ===
BOT_TOKEN = '8413641827:AAFTPHd4DomgKsLniWkWPQEhDGHn2lgOiuA'  # ← DÁN TOKEN CỦA BẠN
CHAT_ID = '6164373385'                              # ← DÁN CHAT_ID CỦA BẠN
bot = Bot(token=BOT_TOKEN)

LEN_RSI = 14
EMA_LEN = 9
WMA_LEN = 45

def get_top_100():
    url = 'https://api.coingecko.com/api/v3/coins/markets'
    params = {'vs_currency': 'usd', 'order': 'market_cap_desc', 'per_page': 100, 'page': 1}
    return requests.get(url, params=params).json()

def get_ohlc(coin_id, days):
    url = f'https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc?vs_currency=usd&days={days}'
    try:
        data = requests.get(url, timeout=10).json()
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.set_index('timestamp')
        return df
    except:
        return None

def calculate_rsi_components(close_series):
    if len(close_series) < max(LEN_RSI, WMA_LEN):
        return None, None, None, None
    rsi = ta.momentum.RSIIndicator(close_series, window=LEN_RSI).rsi()
    rsi = rsi.dropna()
    if len(rsi) < max(EMA_LEN, WMA_LEN):
        return None, None, None, None
    ema_rsi = rsi.ewm(span=EMA_LEN, adjust=False).mean()
    weights = np.arange(1, WMA_LEN + 1)
    wma_rsi = rsi.rolling(WMA_LEN).apply(
        lambda x: np.dot(x, weights[-len(x):]) / weights[-len(x):].sum(), raw=True
    )
    rsi_val = rsi.iloc[-1]
    ema_val = ema_rsi.iloc[-1]
    wma_val = wma_rsi.iloc[-1]
    rsi_series = rsi
    return rsi_val, ema_val, wma_val, rsi_series

def get_status(rsi, ema, wma):
    if rsi > 65 and ema > wma:
        return "Tăng Mạnh"
    elif rsi > 55 and ema > wma:
        return "Tăng"
    elif 46 <= rsi <= 54 and abs(ema - wma) <= 0.5:
        return "Sideway"
    elif rsi < 32 and ema < wma:
        return "Giảm Mạnh"
    elif rsi < 44 and ema < wma:
        return "Giảm"
    else:
        return "Chờ"

def send_alert_with_chart(coin_name, symbol, price, status_w, status_d, df_w, rsi_w_series):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8), gridspec_kw={'height_ratios': [3, 1]})
    ax1.plot(df_w.index, df_w['close'], label='Giá (W)', color='blue', linewidth=1.5)
    ax1.set_title(f'{coin_name} ({symbol.upper()}) - RSI Status W+D', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Giá (USD)')
    ax1.grid(True, alpha=0.3)
    ax1.legend()
    ax2.plot(rsi_w_series.index, rsi_w_series, label='RSI', color='purple', linewidth=1.5)
    ema_line = rsi_w_series.ewm(span=EMA_LEN, adjust=False).mean()
    ax2.plot(ema_line.index, ema_line, label=f'EMA{EMA_LEN}', color='orange', linewidth=1.2)
    wma_line = rsi_w_series.rolling(WMA_LEN).apply(
        lambda x: np.dot(x, np.arange(1, len(x)+1)) / np.arange(1, len(x)+1).sum(), raw=True
    )
    ax2.plot(wma_line.index[-WMA_LEN:], wma_line[-WMA_LEN:], label=f'WMA{WMA_LEN}', color='red', linewidth=1.2)
    ax2.axhline(65, color='darkgreen', linestyle='--', alpha=0.7)
    ax2.axhline(55, color='green', linestyle='--', alpha=0.7)
    ax2.axhline(44, color='red', linestyle='--', alpha=0.7)
    ax2.axhline(32, color='darkred', linestyle='--', alpha=0.7)
    ax2.axhline(50, color='gray', linestyle=':', alpha=0.6)
    ax2.set_ylim(0, 100)
    ax2.set_ylabel('RSI')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    status_color = 'green' if 'Tăng' in status_w else 'red' if 'Giảm' in status_w else 'orange'
    ax2.text(0.02, 0.88, f"W: {status_w}", transform=ax2.transAxes, color=status_color, fontsize=12, fontweight='bold',
             bbox=dict(boxstyle="round,pad=0.3", facecolor=status_color, alpha=0.2))
    ax2.text(0.02, 0.73, f"D: {status_d}", transform=ax2.transAxes, color=status_color, fontsize=12, fontweight='bold',
             bbox=dict(boxstyle="round,pad=0.3", facecolor=status_color, alpha=0.2))
    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    caption = f"""
TRẠNG THÁI CÙNG CHIỀU (W+D)
{coin_name} ({symbol.upper()})
Giá: ${price:,.2f}
W: {status_w}
D: {status_d}
Thời gian: {datetime.now().strftime('%Y-%m-%d %H:%M')}
https://www.coingecko.com/en/coins/{symbol.lower()}
"""
    try:
        bot.send_photo(chat_id=CHAT_ID, photo=buf, caption=caption, parse_mode='HTML')
        print(f"Đã gửi: {coin_name} | {status_w}")
    except Exception as e:
        print(f"Lỗi gửi: {e}")
    finally:
        buf.close()

def scan_top_100():
    print(f"[{datetime.now().strftime('%H:%M')}] Bắt đầu quét...")
    coins = get_top_100()
    alerted = set()
    for coin in coins:
        coin_id = coin['id']
        symbol = coin['symbol']
        name = coin['name']
        price = coin['current_price']
        df_w = get_ohlc(coin_id, days=7)
        df_d = get_ohlc(coin_id, days=1)
        if df_w is None or df_d is None or len(df_w) < 50 or len(df_d) < 20:
            continue
        rsi_w, ema_w, wma_w, rsi_w_series = calculate_rsi_components(df_w['close'])
        rsi_d, ema_d, wma_d, _ = calculate_rsi_components(df_d['close'])
        if None in (rsi_w, ema_w, wma_w, rsi_d, ema_d, wma_d):
            continue
        status_w = get_status(rsi_w, ema_w, wma_w)
        status_d = get_status(rsi_d, ema_d, wma_d)
        if status_w == status_d and status_w not in ["Chờ", "Sideway"]:
            key = f"{symbol}_{status_w}"
            if key not in alerted:
                send_alert_with_chart(name, symbol, price, status_w, status_d, df_w, rsi_w_series)
                alerted.add(key)
                time.sleep(3)
        time.sleep(0.5)
    print(f"Hoàn thành. Gửi {len(alerted)} tín hiệu.\n")

if __name__ == "__main__":
    print("RSI STATUS BOT ĐANG CHẠY...")
    while True:
        try:
            scan_top_100()
        except Exception as e:
            print(f"Lỗi: {e}")
        print("Ngủ 1 giờ...\n")

        time.sleep(3600)

