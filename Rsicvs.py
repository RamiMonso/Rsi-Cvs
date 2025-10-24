# Rsicvs.py
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="RSI Downloader", layout="centered")

st.title("📊 הורדת נתוני סגירה + RSI(14)")
st.markdown("הכנס טיקר, בחר תקופה וסוג גרף – ותקבל קובץ CSV עם מחיר הסגירה וערך RSI(14) בכל נר.")

# --- קלטים מהמשתמש ---
ticker = st.text_input("טיקר (לדוגמה: AAPL)", value="AAPL").upper().strip()

col1, col2 = st.columns(2)
with col1:
    interval_label = st.radio("סוג גרף / אינטרוול:", ("יומי (Daily)", "שיעתי (Hourly)"))
with col2:
    use_adj = st.checkbox("השתמש ב-Adj Close אם קיים (מומלץ)", value=True)

# תקופת נתונים
period_mode = st.selectbox("בחר שיטת בחירת טווח", ("מספר ימים אחורה", "טווח תאריכים"))

if period_mode == "מספר ימים אחורה":
    days = st.number_input("כמה ימים אחורה למשוך?", min_value=1, value=365)
    end = datetime.now().date()
    start = end - timedelta(days=int(days))
else:
    start, end = st.date_input(
        "בחר טווח תאריכים (מתאריך → עד תאריך)",
        value=(datetime.now().date() - timedelta(days=365), datetime.now().date())
    )
    if isinstance(start, tuple) or start > end:
        st.error("אנא ודא ש־Start קטן או שווה ל־End")
        st.stop()

interval = "1d" if interval_label.startswith("יומי") else "1h"

st.markdown(f"**טיקר:** {ticker} | **טווח:** {start} → {end} | **אינטרוול:** {interval}")

# --- פונקציה לחישוב RSI ---
def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.fillna(0)
    rsi[(avg_gain == 0) & (avg_loss == 0)] = np.nan
    rsi[avg_loss == 0] = 100
    return rsi

# --- שליפת נתונים ---
if st.button("📥 משוך נתונים וחישב RSI"):
    if not ticker:
        st.error("אנא הזן טיקר תקף.")
        st.stop()

    try:
        with st.spinner("מושך נתונים מ-Yahoo Finance..."):
            df = yf.download(
                ticker,
                start=pd.to_datetime(start),
                end=pd.to_datetime(end) + pd.Timedelta(days=1),
                interval=interval,
                progress=False,
                threads=True,
                auto_adjust=False
            )
    except Exception as e:
        st.error(f"שגיאה בשליפת נתונים: {e}")
        st.stop()

    if df.empty:
        st.error("לא נמצאו נתונים עבור הטיקר או הטווח שבחרת.")
        st.stop()

    # בחירת מחיר סגירה מתאים
    if use_adj and "Adj Close" in df.columns:
        price_col = "Adj Close"
    else:
        price_col = "Close"

    df = df[[price_col]].rename(columns={price_col: "Close"})
    df.index = pd.to_datetime(df.index)

    # חישוב RSI(14)
    df["RSI_14"] = compute_rsi(df["Close"], period=14)

    # --- ננקה ונאתר את עמודת הזמן ---
    df_reset = df.reset_index()

    # נזהה עמודת זמן לפי שם (Date, Datetime, index וכו')
    time_col = None
    for c in df_reset.columns:
        if "date" in c.lower() or "time" in c.lower():
            time_col = c
            break

    if time_col is not None:
        df_reset.rename(columns={time_col: "Datetime"}, inplace=True)
        df_reset["Datetime"] = pd.to_datetime(df_reset["Datetime"], errors="coerce")
        df_reset["Datetime"] = df_reset["Datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")
    else:
        st.warning("לא נמצאה עמודת זמן — הנתונים יישמרו ללא עמודת תאריך/שעה.")

    # --- הצגה ושמירה ---
    st.success(f"✅ נמשכו {len(df_reset)} שורות בהצלחה.")
    st.dataframe(df_reset.tail(20))

    # יצירת CSV להורדה
    csv = df_reset.to_csv(index=False).encode("utf-8")
    filename = f"{ticker}_RSI14_{start}_{end}.csv"
    st.download_button("📄 הורד קובץ CSV", data=csv, file_name=filename, mime="text/csv")

    # אופציונלי: הורדת Excel
    try:
        import io
        excel_buffer = io.BytesIO()
        df_reset.to_excel(excel_buffer, index=False)
        st.download_button("📘 הורד כקובץ Excel", data=excel_buffer.getvalue(),
                           file_name=filename.replace(".csv", ".xlsx"),
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception:
        pass

    st.markdown("#### הערות:")
    st.markdown("- RSI מחושב לפי שיטת Wilder (EWM עם α=1/14).")
    st.markdown("- אם אין נתוני Adjusted, משמשים ב־Close רגיל.")
    st.markdown("- עבור נתונים שעתיים ייתכן שטווח ההיסטוריה מוגבל ב־Yahoo.")

st.caption("נבנה על ידי ChatGPT GPT-5 · משתמש ב־yfinance, pandas ו־streamlit")
