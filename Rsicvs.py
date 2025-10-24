# app.py
import io
from datetime import date
import pandas as pd
import yfinance as yf
import streamlit as st

st.set_page_config(page_title="YahooHist → Close + RSI(14)", layout="wide")

st.title("הורדת היסטוריית מחיר + RSI(14) מ-Yahoo Finance")
st.markdown(
    "הכנס טיקר, טווח תאריכים ובחר בין גרף **שעה** ל**יום**. התוצאה: טבלת `Close` ו-`RSI(14)` + כפתורי הורדה ל-CSV / Excel."
)

# --- Sidebar inputs ---
with st.sidebar:
    st.header("הגדרות משתמש")
    ticker = st.text_input("1) טיקר (למשל AAPL, MSFT, TSLA)", value="AAPL").upper().strip()
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("2) תאריך התחלה", value=date(2024, 1, 1))
    with col2:
        end_date = st.date_input("3) תאריך סיום", value=date.today())
    interval_choice = st.selectbox("4) בחירת גרף", ["יומי (Daily)", "שעה (Hourly)"])
    st.markdown("---")
    st.write("הגדרות מתקדמות")
    rsi_period = st.number_input("תקופת RSI", min_value=2, max_value=100, value=14)
    fetch_button = st.button("הורד והחשב")

# Utility: map interval
def _interval_from_choice(choice: str) -> str:
    if "Hourly" in choice or "שעה" in choice:
        # yfinance accepts '60m' (or '1h' in some versions) — '60m' is broadly used.
        return "60m"
    return "1d"

# RSI calculation (Wilder's smoothing via EWM)
def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Wilder smoothing: exponential weighted moving average with alpha=1/period
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# Cache the download to avoid repeated network calls during session
@st.cache_data(show_spinner=False)
def download_data(ticker: str, start: date, end: date, interval: str) -> pd.DataFrame:
    # yfinance expects strings for dates
    df = yf.download(ticker, start=start.isoformat(), end=(end.isoformat()), interval=interval, progress=False, auto_adjust=False, threads=True)
    # yfinance returns empty DF sometimes; handle that upstream
    return df

# Main action
if fetch_button:
    if not ticker:
        st.error("אנא הכנס טיקר חוקי.")
    elif start_date > end_date:
        st.error("תאריך התחלה חייב להיות לפני תאריך סיום.")
    else:
        interval = _interval_from_choice(interval_choice)
        status_text = st.empty()
        with st.spinner("מוריד נתונים מ-Yahoo Finance..."):
            try:
                raw = download_data(ticker, start_date, end_date, interval)
            except Exception as e:
                st.exception(f"שגיאה בעת הורדת הנתונים: {e}")
                raw = pd.DataFrame()

        if raw.empty:
            st.warning("לא נמצאו נתונים עבור הטווח/טיקר המבוקש. נסה טווח אחר או טיקר אחר.")
        else:
            # Ensure datetime index and sort
            df = raw.copy()
            if not isinstance(df.index, pd.DatetimeIndex):
                try:
                    df.index = pd.to_datetime(df.index)
                except Exception:
                    pass
            df = df.sort_index()

            # Get Close
            df_res = df[["Close"]].copy()
            df_res.index.name = "Datetime"

            # Compute RSI
            df_res[f"RSI_{rsi_period}"] = compute_rsi(df_res["Close"], period=rsi_period)
            # Round for readability
            df_res["Close"] = df_res["Close"].round(4)
            df_res[f"RSI_{rsi_period}"] = df_res[f"RSI_{rsi_period}"].round(2)

            # Display top/bottom controls
            st.success(f"נמצאו {len(df_res)} שורות — טווח: {df_res.index[0].strftime('%Y-%m-%d %H:%M')} → {df_res.index[-1].strftime('%Y-%m-%d %H:%M')}")
            # Add filter for preview rows
            rows_to_show = st.slider("הצג שורות (Preview)", min_value=5, max_value=1000, value=25, step=5)
            st.dataframe(df_res.tail(rows_to_show))

            # Prepare downloads
            csv_bytes = df_res.to_csv(index=True).encode("utf-8")
            # Excel in-memory
            towrite = io.BytesIO()
            with pd.ExcelWriter(towrite, engine="openpyxl") as writer:
                df_res.to_excel(writer, sheet_name="Close_RSI", index=True)
                writer.save()
            towrite.seek(0)
            excel_bytes = towrite.read()

            col_download_1, col_download_2 = st.columns([1,1])
            with col_download_1:
                st.download_button(
                    label="הורד CSV",
                    data=csv_bytes,
                    file_name=f"{ticker}_{start_date.isoformat()}_{end_date.isoformat()}_{interval}.csv",
                    mime="text/csv",
                )
            with col_download_2:
                st.download_button(
                    label="הורד Excel (.xlsx)",
                    data=excel_bytes,
                    file_name=f"{ticker}_{start_date.isoformat()}_{end_date.isoformat()}_{interval}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

            # Optional: show last 100 rows chart (Close)
            if st.checkbox("הצג גרף מחיר סגירה אחרונים"):
                st.line_chart(df_res["Close"].tail(500))

# Footer / instructions
st.write("---")
st.markdown(
    """
    **הערות ו-Tips**
    - נתונים_intraday (שעה) מתאפשרים לעיתים בטווחים קצרים יותר בהתאם למגבלות Yahoo Finance.
    - אם תרצה להוסיף אינדיקטורים נוספים (EMA, MACD, Bollinger וכו') תגיד ואוסיף.
    - לפרסום ב-GitHub: הוסף קובץ `requirements.txt` (דוגמא למטה) ו-`app.py` זהו.
    """
)
