# app.py
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="הורדת Close + RSI(14)", layout="centered")

st.title("הורדת נתוני סגירה + RSI(14)")
st.markdown("הכנס טיקר (למשל: AAPL), בחר תקופה וסוג גרף — תקבל קובץ CSV עם Close ו-RSI(14) לכל נר.")

# --- Inputs ---
ticker = st.text_input("טיקר (Ticker)", value="AAPL").upper().strip()

col1, col2 = st.columns(2)
with col1:
    grp_type = st.radio("סוג גרף / אינטרוול", ("יומי (Daily)", "שיעתי (Hourly)"))
with col2:
    use_adj = st.checkbox("השתמש ב-Adj Close אם קיים (ברירת מחדל: כן)", value=True)

# תקופה: אפשר לבחור בין פרקי זמן סטנדרטיים או טווח תאריכים
period_mode = st.selectbox("בחר תקופת נתונים", ("Last N days (מספר ימים אחורה)", "טווח תאריכים"))

if period_mode == "Last N days (מספר ימים אחורה)":
    days = st.number_input("כמה ימים אחורה למשוך?", min_value=1, value=365, step=1)
    end = datetime.now().date()
    start = end - timedelta(days=int(days))
else:
    start, end = st.date_input("בחר טווח תאריכים (Start, End)", 
                               value=(datetime.now().date() - timedelta(days=365), datetime.now().date()))
    # אם המשתמש הקל逆, נוודא start <= end
    if isinstance(start, tuple) or start > end:
        st.error("אנא ודא ש-Start ≤ End")
        st.stop()

# Map chart type to yfinance interval
interval = "1d" if grp_type.startswith("יומי") else "1h"

st.markdown(f"**טיקר:** {ticker}  •  **טווח:** {start} → {end}  •  **אינטרוול:** {interval}")

# --- RSI calculation (Wilder / EWM approach) ---
def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder smoothing via EWM with alpha = 1/period
    avg_gain = gain.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    # handle zero loss
    rsi = rsi.fillna(0)
    rsi[(avg_gain == 0) & (avg_loss == 0)] = np.nan  # if no movement, keep NaN
    rsi[avg_loss == 0] = 100  # avoid division by zero -> RSI = 100
    return rsi

# --- Fetch data ---
if st.button("משוך נתונים וחישב CSV"):
    if not ticker:
        st.error("אנא הזן טיקר תקף.")
        st.stop()

    # yfinance period parameter can accept start/end; we'll use start/end to be explicit
    try:
        with st.spinner("מושך נתונים מ-Yahoo Finance..."):
            df = yf.download(ticker, start=pd.to_datetime(start), end=pd.to_datetime(end) + pd.Timedelta(days=1),
                             interval=interval, progress=False, threads=True, auto_adjust=False)
    except Exception as e:
        st.error(f"שגיאה בשליפת נתונים: {e}")
        st.stop()

    if df.empty:
        st.error("לא נמצאו נתונים עבור הטווח/טיקר הנתון. נסה טווח תאריכים אחר או טיקר אחר.")
        st.stop()

    # בחר מחיר לסגירה — Adjusted Close אם רוצים ויש
    if use_adj and "Adj Close" in df.columns:
        price_col = "Adj Close"
    else:
        # yfinance for intraday may not have 'Adj Close'; use 'Close'
        price_col = "Close"

    # ודא שיש עמודת Close/Adj Close
    if price_col not in df.columns:
        st.error(f"העמודה {price_col} לא נמצאה בנתונים שחזרו.")
        st.stop()

    df = df[[price_col]].rename(columns={price_col: "Close"})
    # אם האינדקס הוא timezone-aware, נפשט אותו לתחום תאריכים רגיל (UTC או מקומי לפי הצורך)
    df.index = pd.to_datetime(df.index)

    # חישוב RSI(14)
    df["RSI_14"] = compute_rsi(df["Close"], period=14)

    # שמירה והצגה
    df_reset = df.reset_index().rename(columns={"index": "Datetime"})
    # יחלץ תאריכים בזמן ISO
    df_reset["Datetime"] = df_reset["Datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")

    # הצגה בסיסית
    st.success(f"נמשכו {len(df_reset)} שורות.")
    st.dataframe(df_reset.tail(20))

    # CSV להורדה
    csv = df_reset.to_csv(index=False).encode("utf-8")
    filename = f"{ticker}_close_rsi14_{start}_{end}.csv"
    st.download_button("הורד CSV", data=csv, file_name=filename, mime="text/csv")

    # אופציונלי: הורדת קובץ Excel
    try:
        import io
        excel_buffer = io.BytesIO()
        df_reset.to_excel(excel_buffer, index=False)
        st.download_button("הורד כ-Excel", data=excel_buffer.getvalue(), file_name=filename.replace(".csv", ".xlsx"), mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception:
        # אם אין openpyxl/xlsxwriter, נדלג
        pass

    st.markdown("**הערות:**")
    st.markdown("- RSI מחושב בעזרת Wilder smoothing (EWM עם α=1/14).")
    st.markdown("- אם אין נתוני Adjusted עבור טווח/אינטרוול מסוים, המערכת משתמשת ב-Close.")
    st.markdown("- לנתונים שעתיים/דקותיים יש הגבלות היסטוריות ב-Yahoo; אם לא מופיעים נתונים רבים ל-'1h', נסה טווח קצר יותר.")

st.caption("נבנה ב-Python  (streamlit + yfinance + pandas).")
