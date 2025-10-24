# app.py - Streamlit app: Yahoo Finance → Close + RSI(14)
# כולל: בחירה בין Close/Adj Close, וחישוב RSI בשיטת Wilder (SMA התחלתית)
import io
from datetime import date, timedelta
import numpy as np
import pandas as pd
import yfinance as yf
import streamlit as st

st.set_page_config(page_title="YahooHist → Close + RSI(14)", layout="wide")

# ---------- Helpers ----------
def _interval_from_choice(choice: str) -> str:
    return "60m" if choice == "שעה (Hourly)" else "1d"

def rsi_wilder(prices: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI calculation using Wilder's smoothing:
    1) Compute deltas, gains and losses
    2) First average gain/loss = SMA of first `period` values
    3) Subsequent averages: prev_avg * (period-1) / period + current_gain/loss / period
    Returns a Series same index as `prices`.
    """
    prices = prices.dropna()
    if prices.empty:
        return pd.Series(dtype="float64")

    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    # Prepare arrays
    gain_vals = gain.to_numpy()
    loss_vals = loss.to_numpy()

    rsi = np.full_like(gain_vals, fill_value=np.nan, dtype="float64")

    # Need at least period+1 points to compute first RSI value (because first diff yields NaN)
    if len(prices) <= period:
        return pd.Series(rsi, index=prices.index)

    # First average (SMA) computed on gains[1:period]?? Standard approach: use first `period` deltas (skip the NaN at index 0)
    # We'll compute SMA over gains[1:period+1] (i.e., the first `period` non-NaN delta values)
    # Indices: gains[1] .. gains[period] inclusive -> total `period` values
    first_gain_avg = np.mean(gain_vals[1: period+1])
    first_loss_avg = np.mean(loss_vals[1: period+1])

    avg_gain = first_gain_avg
    avg_loss = first_loss_avg

    # RSI for the point at index period (i.e., corresponding to prices.index[period])
    # Compute RS and RSI
    if avg_loss == 0:
        rs = np.inf
        rsi_val = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi_val = 100.0 - (100.0 / (1.0 + rs))
    rsi[period] = rsi_val

    # Now iterate forward and apply Wilder smoothing
    for i in range(period + 1, len(gain_vals)):
        g = gain_vals[i]
        l = loss_vals[i]
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period

        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))

    # Return Series aligned to original (NaN where undefined)
    return pd.Series(rsi, index=prices.index)

@st.cache_data(show_spinner=False)
def download_data(ticker: str, start: date, end: date, interval: str, auto_adjust: bool = False) -> pd.DataFrame:
    """
    Download historical data using yfinance.download.
    If auto_adjust=True, yfinance returns adjusted close as 'Close' (and drops 'Adj Close').
    To be explicit, we request auto_adjust=False (so we can show both Close and Adj Close if available),
    but allow caller to set auto_adjust if desired.
    """
    # For daily intervals we add one day to end so the requested end date is included
    end_param = (end + timedelta(days=1)).isoformat() if interval == "1d" else end.isoformat()
    df = yf.download(
        ticker,
        start=start.isoformat(),
        end=end_param,
        interval=interval,
        progress=False,
        threads=True,
        auto_adjust=False,  # we keep raw Close and Adj Close so user can choose which to use
        actions=False
    )
    return df

def make_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=True).encode("utf-8")

def make_excel_bytes(df: pd.DataFrame) -> bytes:
    towrite = io.BytesIO()
    with pd.ExcelWriter(towrite, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Close_RSI", index=True)
    towrite.seek(0)
    return towrite.read()

# ---------- Page layout ----------
st.title("Yahoo Finance — Close + RSI(14) (Wilder)")
st.markdown(
    "כאן אפשר לבחור האם לחשב RSI על בסיס `Adj Close` (מחירים מתוקנים) או `Close` (לא מתוקנים), ולראות את שתי העמודות לצורך השוואה."
)

left_col, right_col = st.columns([1, 2])

# ---------- Left column: form ----------
with left_col:
    st.header("הגדרות חיפוש")
    example_fill = st.button("מלא דוגמה (AAPL, 90 יום אחרונים)")

    with st.form("input_form", clear_on_submit=False):
        ticker = st.text_input(
            "טיקר (ללא שוק)",
            value=st.session_state.get("ticker", "AAPL"),
            max_chars=24,
            help="לדוגמה: AAPL, MSFT, TSLA. ניתן להשתמש גם ב-EXCHANGE:TICKER אם נדרש."
        )
        col_a, col_b = st.columns(2)
        with col_a:
            start_date = st.date_input(
                "תאריך התחלה",
                value=st.session_state.get("start_date", date.today() - timedelta(days=90))
            )
        with col_b:
            end_date = st.date_input(
                "תאריך סיום",
                value=st.session_state.get("end_date", date.today())
            )
        interval_choice = st.radio(
            "בחירת גרף",
            ("יומי (Daily)", "שעה (Hourly)"),
            index=0 if st.session_state.get("interval_choice", "יומי (Daily)") == "יומי (Daily)" else 1,
            help="נתוני 'שעה' עשויים להיות זמינים לטווחים קצרים בלבד."
        )
        rsi_period = st.number_input(
            "תקופת RSI",
            min_value=2, max_value=100, value=st.session_state.get("rsi_period", 14)
        )
        use_adj = st.checkbox(
            "השתמש ב-Adj Close לחישוב (מומלץ להתאמה לגרפים של Yahoo)",
            value=st.session_state.get("use_adj", True)
        )
        include_ohlcv = st.checkbox(
            "הצג עמודות נוספות (Open/High/Low/Volume)",
            value=st.session_state.get("include_ohlcv", False)
        )
        submit = st.form_submit_button("הורד והצג")

    if example_fill:
        st.session_state["ticker"] = "AAPL"
        st.session_state["start_date"] = date.today() - timedelta(days=90)
        st.session_state["end_date"] = date.today()
        st.session_state["interval_choice"] = "יומי (Daily)"
        st.session_state["rsi_period"] = 14
        st.session_state["use_adj"] = True
        st.session_state["include_ohlcv"] = False
        st.experimental_rerun()

    if submit:
        st.session_state["ticker"] = ticker.strip().upper()
        st.session_state["start_date"] = start_date
        st.session_state["end_date"] = end_date
        st.session_state["interval_choice"] = interval_choice
        st.session_state["rsi_period"] = int(rsi_period)
        st.session_state["use_adj"] = bool(use_adj)
        st.session_state["include_ohlcv"] = include_ohlcv

    st.markdown("---")
    st.write("טיפים:")
    st.write("- אם ברצונך שהתוצאות יתאימו ל-Google/Yahoo charts — השתמש ב-Adj Close.")
    st.write("- נתונים אינטרדיי (שעה) יכולים להיות מוגבלים לטווחים קצרים.")

# ---------- Right column: results / status ----------
with right_col:
    st.header("תוצאות")
    has_input = all(k in st.session_state for k in ("ticker", "start_date", "end_date", "interval_choice", "rsi_period", "use_adj"))
    if not has_input:
        st.info("מלא את הפרטים משמאל ולחץ 'הורד והצג' כדי להתחיל.")
    else:
        ticker = st.session_state["ticker"]
        start_date = st.session_state["start_date"]
        end_date = st.session_state["end_date"]
        interval_choice = st.session_state["interval_choice"]
        rsi_period = st.session_state["rsi_period"]
        use_adj = st.session_state["use_adj"]
        include_ohlcv = st.session_state.get("include_ohlcv", False)

        # Basic validations
        if not ticker:
            st.error("שגיאה: טיקר ריק — אנא הכנס טיקר תקין.")
        elif start_date > end_date:
            st.error("שגיאה: תאריך התחלה חייב להיות לפני תאריך סיום.")
        else:
            interval = _interval_from_choice(interval_choice)
            try:
                with st.spinner("מוריד נתונים מ-Yahoo Finance..."):
                    raw = download_data(ticker, start_date, end_date, interval)
            except Exception as e:
                st.error(f"שגיאה בעת הורדת הנתונים: {e}")
                raw = pd.DataFrame()

            if raw.empty:
                st.warning(
                    "לא נמצאו נתונים בטווח/לטיקר המבוקש. הצעות:\n"
                    "- ודא שהטיקר תקין (נסה ללא תוספת שוק).\n"
                    "- נסה טווח זמן קצר יותר (בעיקר עבור אינטרדיי).\n"
                    "- נסה טיקר ידוע (AAPL, MSFT) לצורך בדיקה."
                )
            else:
                df = raw.copy()
                # ודא אינדקס מסוג DatetimeIndex
                if not isinstance(df.index, pd.DatetimeIndex):
                    df.index = pd.to_datetime(df.index)
                df = df.sort_index()

                # Ensure Adj Close exists for comparison; yfinance returns 'Adj Close' if available
                has_adj = "Adj Close" in df.columns

                # Build result frame: optionally include OHLCV, show Close and Adj Close (if present)
                cols = []
                if include_ohlcv:
                    for c in ("Open", "High", "Low", "Volume"):
                        if c in df.columns:
                            cols.append(c)
                # Always attempt to include Close and Adj Close (if present)
                if "Close" in df.columns:
                    cols.append("Close")
                if has_adj:
                    cols.append("Adj Close")

                df_res = df[cols].copy()
                df_res.index.name = "Datetime"

                # Choose price series for RSI calculation
                price_series_for_rsi = None
                if use_adj and has_adj:
                    price_series_for_rsi = df_res["Adj Close"]
                    source_used = "Adj Close"
                elif "Close" in df_res.columns:
                    price_series_for_rsi = df_res["Close"]
                    source_used = "Close"
                else:
                    st.error("אין עמודת מחיר זמינה לחישוב RSI.")
                    price_series_for_rsi = None
                    source_used = "None"

                # Compute RSI using Wilder's method
                if price_series_for_rsi is not None:
                    rsi_series = rsi_wilder(price_series_for_rsi, period=rsi_period)
                    df_res[f"RSI_{rsi_period}"] = rsi_series

                    # Round numeric columns safely
                    numeric_cols = df_res.select_dtypes(include="number").columns
                    for col in numeric_cols:
                        if str(col).startswith("RSI"):
                            df_res[col] = df_res[col].round(2)
                        else:
                            df_res[col] = df_res[col].round(4)

                    # Save last df for download
                    st.session_state["last_df"] = df_res

                    # Display info
                    st.success(
                        f"נמצאו {len(df_res)} שורות — חישוב RSI על בסיס: {source_used} — "
                        f"טווח: {df_res.index[0].strftime('%Y-%m-%d %H:%M')} → {df_res.index[-1].strftime('%Y-%m-%d %H:%M')}"
                    )

                    preview_count = st.slider(
                        "הצג שורות (Preview)",
                        min_value=5,
                        max_value=min(1000, len(df_res)),
                        value=min(25, len(df_res)),
                        step=5
                    )
                    st.dataframe(df_res.tail(preview_count), use_container_width=True)

                    # Graphs
                    with st.expander("הצג גרפים"):
                        st.line_chart(df_res["Close"].dropna().tail(500)) if "Close" in df_res.columns else None
                        if has_adj:
                            st.line_chart(df_res["Adj Close"].dropna().tail(500))
                        st.line_chart(df_res[f"RSI_{rsi_period}"].dropna().tail(500))

                    # Downloads
                    try:
                        csv_bytes = make_csv_bytes(df_res)
                        excel_bytes = make_excel_bytes(df_res)
                    except Exception as e:
                        st.error(f"שגיאה בהכנת קבצים להורדה: {e}")
                        csv_bytes = None
                        excel_bytes = None

                    dl_col1, dl_col2 = st.columns(2)
                    with dl_col1:
                        if csv_bytes:
                            st.download_button(
                                label="הורד כ-CSV",
                                data=csv_bytes,
                                file_name=f"{ticker}_{start_date.isoformat()}_{end_date.isoformat()}_{interval}.csv",
                                mime="text/csv",
                            )
                        else:
                            st.button("CSV לא זמין", disabled=True)
                    with dl_col2:
                        if excel_bytes:
                            st.download_button(
                                label="הורד כ-Excel (.xlsx)",
                                data=excel_bytes,
                                file_name=f"{ticker}_{start_date.isoformat()}_{end_date.isoformat()}_{interval}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            )
                        else:
                            st.button("Excel לא זמין", disabled=True)
                else:
                    st.error("לא הוגדר מחיר לחישוב RSI.")

# ---------- Footer ----------
st.markdown("***")
st.caption("הערה: למרות מאמצינו להתאים את החישוב לגרפים ציבוריים, ייתכנו הבדלים קלים בין פלטפורמות שונות (שיטות התחשיב התחלתיות, התאמות דיוק, או עדכוני נתונים). אם תרצה, אוכל להשוות ערכי RSI בין שיטות (SMA start / EWM / Wilder) ולייצא קולומות להשוואה.")
