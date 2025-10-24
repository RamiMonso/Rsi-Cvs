# app.py (UI/UX משופר)
import io
from datetime import date, timedelta
import pandas as pd
import yfinance as yf
import streamlit as st

st.set_page_config(page_title="YahooHist → Close + RSI(14)", layout="wide")

# ---------- Helpers ----------
def _interval_from_choice(choice: str) -> str:
    return "60m" if choice == "שעה (Hourly)" else "1d"

def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

@st.cache_data(show_spinner=False)
def download_data(ticker: str, start: date, end: date, interval: str) -> pd.DataFrame:
    # yfinance: end is exclusive for some endpoints; add one day to include end-date for daily
    # but keep original behavior for intraday (it accepts datetime ranges)
    df = yf.download(ticker, start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(), interval=interval, progress=False, threads=True)
    return df

def make_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=True).encode("utf-8")

def make_excel_bytes(df: pd.DataFrame) -> bytes:
    towrite = io.BytesIO()
    with pd.ExcelWriter(towrite, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Close_RSI", index=True)
        writer.save()
    towrite.seek(0)
    return towrite.read()

# ---------- Page layout ----------
st.title("Yahoo Finance — Close + RSI(14)")
st.markdown(
    "הכנס טיקר, טווח תאריכים ובחר גרף (יומי/שעה). תתקבל טבלה של `Close` ו-`RSI(14)` לכל נר, וכן כפתורי הורדה ל-CSV/Excel."
)

left_col, right_col = st.columns([1, 2])

# ---------- Left column: form ----------
with left_col:
    st.header("הגדרות חיפוש")
    # Quick examples to help the user
    example_fill = st.button("מלא דוגמה (AAPL, 30 יום אחרונים)")
    # Use a form to group inputs and submit together
    with st.form("input_form", clear_on_submit=False):
        ticker = st.text_input("טיקר (ללא שוק)", value="AAPL", max_chars=12,
                               help="לדוגמה: AAPL, MSFT, TSLA. אם צריך שוק (למשל LON:VOD) הכנס לפי הצורך.")
        col_a, col_b = st.columns(2)
        with col_a:
            start_date = st.date_input("תאריך התחלה", value=date.today() - timedelta(days=30))
        with col_b:
            end_date = st.date_input("תאריך סיום", value=date.today())
        interval_choice = st.radio("בחירת גרף", ("יומי (Daily)", "שעה (Hourly)"),
                                   help="שימו לב: נתוני 'שעה' עשויים להיות זמינים בטווחים קצרים בלבד ב-Yahoo Finance.")
        rsi_period = st.number_input("תקופת RSI", min_value=2, max_value=100, value=14, step=1)
        include_ohlcv = st.checkbox("הצג עמודות נוספות (Open/High/Low/Volume)", value=False)
        submit = st.form_submit_button("הורד והצג")

    # If user pressed example, fill defaults (via session_state)
    if example_fill:
        st.session_state["ticker"] = "AAPL"
        st.session_state["start_date"] = date.today() - timedelta(days=30)
        st.session_state["end_date"] = date.today()
        st.session_state["interval_choice"] = "יומי (Daily)"
        # reflect into UI (this updates fields after rerun)
        st.experimental_rerun()

    # Persist form values into session_state for use outside the form
    if submit:
        st.session_state["ticker"] = ticker.strip().upper()
        st.session_state["start_date"] = start_date
        st.session_state["end_date"] = end_date
        st.session_state["interval_choice"] = interval_choice
        st.session_state["rsi_period"] = int(rsi_period)
        st.session_state["include_ohlcv"] = include_ohlcv

    st.markdown("---")
    st.write("טיפים:")
    st.write("- עבור נתונים שעתיים/דקה — ייתכן ש-Yahoo מגביל טווחי זמן. אם לא קיבלת תוצאות — צמצם את התקופה.")
    st.write("- ניתן להשתמש ב-`TICKER` בלבד (לרוב עובד), או בפורמט `EXCHANGE:TICKER` כאשר יש צורך.")

# ---------- Right column: results / status ----------
with right_col:
    st.header("תוצאות")
    # Validate that we have form values to proceed
    has_input = all(k in st.session_state for k in ("ticker", "start_date", "end_date", "interval_choice", "rsi_period"))
    if not has_input:
        st.info("מלא את הפרטים משמאל ולחץ 'הורד והצג' כדי להתחיל.")
    else:
        # Extract values
        ticker = st.session_state["ticker"]
        start_date = st.session_state["start_date"]
        end_date = st.session_state["end_date"]
        interval_choice = st.session_state["interval_choice"]
        rsi_period = st.session_state["rsi_period"]
        include_ohlcv = st.session_state.get("include_ohlcv", False)

        # Basic validations
        if not ticker:
            st.error("שגיאה: טיקר ריק — אנא הכנס טיקר תקין.")
        elif start_date > end_date:
            st.error("שגיאה: תאריך התחלה חייב להיות לפני תאריך סיום.")
        else:
            # Download and compute
            interval = _interval_from_choice(interval_choice)
            try:
                with st.spinner("מוריד נתונים מ-Yahoo Finance..."):
                    raw = download_data(ticker, start_date, end_date, interval)
            except Exception as e:
                st.error(f"שגיאה בעת הורדת הנתונים: {e}")
                raw = pd.DataFrame()

            if raw.empty:
                st.warning("לא נמצאו נתונים בטווח/לטיקר המבוקש. הצעות:\n"
                           "- בדוק שהטיקר נכון (נסה ללא תוסף שוק).\n"
                           "- נסה טווח זמן קצר יותר (בעיקר עבור נתונים שעתיים).\n"
                           "- נסה טיקר ידוע לצורך בדיקה (AAPL, MSFT).")
            else:
                df = raw.copy()
                # Ensure datetime index
                if not isinstance(df.index, pd.DatetimeIndex):
                    df.index = pd.to_datetime(df.index)
                df = df.sort_index()

                # Prepare result frame
                cols_to_keep = ["Close"]
                if include_ohlcv:
                    for c in ("Open", "High", "Low", "Volume"):
                        if c in df.columns:
                            cols_to_keep.insert(0, c)  # show OHLCV before Close
                df_res = df[cols_to_keep].copy()
                df_res.index.name = "Datetime"
                # RSI
                df_res[f"RSI_{rsi_period}"] = compute_rsi(df_res["Close"], period=rsi_period)
                # Round numeric values for display
                for c in df_res.select_dtypes(include="number").columns:
                    if c.startswith("RSI"):
                        df_res[c] = df_res[c].round(2)
                    else:
                        df_res[c] = df_res[c].round(4)

                # Save to session for downloads
                st.session_state["last_df"] = df_res

                # Display summary and dataframe
                st.success(f"נמצאו {len(df_res)} שורות — טווח: {df_res.index[0].strftime('%Y-%m-%d %H:%M')} → {df_res.index[-1].strftime('%Y-%m-%d %H:%M')}")
                # Controls for preview
                preview_count = st.slider("הצג שורות (Preview)", min_value=5, max_value=min(1000, len(df_res)), value=min(25, len(df_res)), step=5)
                st.dataframe(df_res.tail(preview_count), use_container_width=True)

                # Chart area
                with st.expander("הצג גרפים"):
                    st.line_chart(df_res["Close"].tail(500))
                    st.line_chart(df_res[f"RSI_{rsi_period}"].tail(500))

                # Download buttons
                csv_bytes = make_csv_bytes(df_res)
                excel_bytes = make_excel_bytes(df_res)
                dl_col1, dl_col2 = st.columns(2)
                with dl_col1:
                    st.download_button(
                        label="הורד כ-CSV",
                        data=csv_bytes,
                        file_name=f"{ticker}_{start_date.isoformat()}_{end_date.isoformat()}_{interval}.csv",
                        mime="text/csv",
                    )
                with dl_col2:
                    st.download_button(
                        label="הורד כ-Excel (.xlsx)",
                        data=excel_bytes,
                        file_name=f"{ticker}_{start_date.isoformat()}_{end_date.isoformat()}_{interval}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

# ---------- Footer ----------
st.markdown("***")
st.caption("הערה: נתוני 'שעה' יכולים להיות מוגבלים ל-30 יום או פחות בהתאם ל-Yahoo Finance. אם תרצה, אני יכול להוסיף בדיקה אוטומטית שתמנע בקשות לטווחים ארוכים עבור אינטרוולים אינטרדיי.")
