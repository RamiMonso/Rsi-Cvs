# app.py - Streamlit app: Yahoo Finance → Close + RSI(14) with warmup
# העתק/הדבק והריץ: streamlit run app.py
import io
from datetime import date, timedelta
import numpy as np
import pandas as pd
import yfinance as yf
import streamlit as st

st.set_page_config(page_title="YahooHist → Close + RSI(14) with Warmup", layout="wide")

# ---------- Helpers ----------
def _interval_from_choice(choice: str) -> str:
    return "60m" if choice == "שעה (Hourly)" else "1d"

def rsi_wilder(prices, period: int = 14) -> pd.Series:
    """
    RSI calculation using Wilder's smoothing with SMA start.
    Robust to receiving a DataFrame (will use first column) or a Series.
    Returns a pandas.Series aligned to the input Series index (NaN where undefined).
    """
    if isinstance(prices, pd.DataFrame):
        if prices.shape[1] == 0:
            return pd.Series(dtype="float64")
        prices = prices.iloc[:, 0]

    prices = pd.Series(prices).copy()
    orig_index = prices.index

    prices_numeric = prices.astype(float)
    prices_no_na = prices_numeric.dropna()
    n = len(prices_no_na)

    result = pd.Series(index=orig_index, data=np.nan, dtype="float64")
    if n <= period:
        return result

    delta = prices_no_na.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    gain_vals = gain.to_numpy()
    loss_vals = loss.to_numpy()

    rsi_vals = np.full(len(gain_vals), np.nan, dtype="float64")

    first_gain_avg = np.mean(gain_vals[1: period + 1])
    first_loss_avg = np.mean(loss_vals[1: period + 1])

    avg_gain = float(first_gain_avg)
    avg_loss = float(first_loss_avg)

    if avg_loss == 0.0:
        rsi_vals[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi_vals[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period + 1, len(gain_vals)):
        g = gain_vals[i] if not np.isnan(gain_vals[i]) else 0.0
        l = loss_vals[i] if not np.isnan(loss_vals[i]) else 0.0
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period

        if avg_loss == 0.0:
            rsi_vals[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_vals[i] = 100.0 - (100.0 / (1.0 + rs))

    rsi_series_no_na = pd.Series(rsi_vals, index=prices_no_na.index)

    for idx, val in rsi_series_no_na.items():
        result.at[idx] = val

    return result

@st.cache_data(show_spinner=False)
def download_data(ticker: str, start: date, end: date, interval: str) -> pd.DataFrame:
    """
    Download historical data using yfinance.download.
    For daily intervals, add one day to 'end' param to include the end date.
    Keep auto_adjust=False so we have both Close and Adj Close.
    """
    end_param = (end + timedelta(days=1)).isoformat() if interval == "1d" else end.isoformat()
    df = yf.download(
        ticker,
        start=start.isoformat(),
        end=end_param,
        interval=interval,
        progress=False,
        threads=True,
        auto_adjust=False,
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
st.title("Yahoo Finance — Close + RSI(14) with Warmup")
st.markdown(
    "בחר טיקר, טווח, אינטרוול ובצע 'חימום' (warmup) של X ימים לפני התאריך שבחרת — כך ה-RSI של היום הראשון יחושב מתוך היסטוריה ארוכה."
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

        st.markdown("**Warmup (חימום) ל-RSI**")
        warmup_enabled = st.checkbox("הפעל חימום ל-RSI", value=True, help="אם מסומן - יוריד נתונים נוספים לפני תאריך ההתחלה לחישוב RSI מדויק.")
        warmup_days = st.number_input("מספר ימים לחימום (לדוגמה 1000)", min_value=0, max_value=5000, value=st.session_state.get("warmup_days", 1000), step=1)

        submit = st.form_submit_button("הורד והצג")

    if example_fill:
        st.session_state["ticker"] = "AAPL"
        st.session_state["start_date"] = date.today() - timedelta(days=90)
        st.session_state["end_date"] = date.today()
        st.session_state["interval_choice"] = "יומי (Daily)"
        st.session_state["rsi_period"] = 14
        st.session_state["use_adj"] = True
        st.session_state["include_ohlcv"] = False
        st.session_state["warmup_days"] = 1000
        st.session_state["warmup_enabled"] = True
        st.experimental_rerun()

    if submit:
        st.session_state["ticker"] = ticker.strip().upper()
        st.session_state["start_date"] = start_date
        st.session_state["end_date"] = end_date
        st.session_state["interval_choice"] = interval_choice
        st.session_state["rsi_period"] = int(rsi_period)
        st.session_state["use_adj"] = bool(use_adj)
        st.session_state["include_ohlcv"] = include_ohlcv
        st.session_state["warmup_enabled"] = bool(warmup_enabled)
        st.session_state["warmup_days"] = int(warmup_days)

    st.markdown("---")
    st.write("טיפים:")
    st.write("- עבור התאמה לגרפים ציבוריים השתמש ב-Adj Close.")
    st.write("- חימום גדול עובד טוב עבור נתונים יומיים; עבור נתוני אינטרדיי יכול להיות מוגבל.")

# ---------- Right column: results / status ----------
with right_col:
    st.header("תוצאות")
    has_input = all(k in st.session_state for k in ("ticker", "start_date", "end_date", "interval_choice", "rsi_period", "use_adj", "warmup_enabled", "warmup_days"))
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
        warmup_enabled = st.session_state["warmup_enabled"]
        warmup_days = st.session_state["warmup_days"]

        if not ticker:
            st.error("שגיאה: טיקר ריק — אנא הכנס טיקר תקין.")
        elif start_date > end_date:
            st.error("שגיאה: תאריך התחלה חייב להיות לפני תאריך סיום.")
        else:
            interval = _interval_from_choice(interval_choice)

            # Determine download start considering warmup
            if warmup_enabled and warmup_days > 0:
                # For intraday, cap warmup to a safer default (Yahoo often limits intraday history)
                if interval == "60m" and warmup_days > 60:
                    capped = 60
                    st.warning(f"נתוני אינטרדיי מוגבלים בדרך כלל — חימום שביקשת ({warmup_days} ימים) גדול מדי עבור hourly. בוצע קיזוז ל־{capped} ימים במקום.")
                    eff_warmup_days = capped
                else:
                    eff_warmup_days = warmup_days
                download_start = start_date - timedelta(days=eff_warmup_days)
            else:
                download_start = start_date

            # Download extended data
            try:
                with st.spinner("מוריד נתונים מ-Yahoo Finance (כולל חימום אם נבחר)..."):
                    raw = download_data(ticker, download_start, end_date, interval)
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
                if not isinstance(df.index, pd.DatetimeIndex):
                    df.index = pd.to_datetime(df.index)
                df = df.sort_index()

                has_adj = "Adj Close" in df.columns

                cols = []
                if include_ohlcv:
                    for c in ("Open", "High", "Low", "Volume"):
                        if c in df.columns:
                            cols.append(c)
                if "Close" in df.columns:
                    cols.append("Close")
                if has_adj:
                    cols.append("Adj Close")

                df_res_full = df[cols].copy()
                df_res_full.index.name = "Datetime"

                # choose price series (from extended data)
                if use_adj and has_adj:
                    price_series_for_rsi = df_res_full["Adj Close"]
                    source_used = "Adj Close"
                elif "Close" in df_res_full.columns:
                    price_series_for_rsi = df_res_full["Close"]
                    source_used = "Close"
                else:
                    st.error("אין עמודת מחיר זמינה לחישוב RSI.")
                    price_series_for_rsi = None
                    source_used = "None"

                if price_series_for_rsi is not None:
                    # compute RSI on the extended series
                    rsi_series_full = rsi_wilder(price_series_for_rsi, period=rsi_period)
                    df_res_full[f"RSI_{rsi_period}"] = rsi_series_full

                    # Now trim to user-visible window: from start_date -> end_date
                    view_mask = (df_res_full.index >= pd.to_datetime(start_date)) & (df_res_full.index <= pd.to_datetime(end_date) + pd.Timedelta(days=1))
                    df_view = df_res_full.loc[view_mask].copy()
                    # Note: for intraday the +1 day may include extra; but it's safe to then slice by <= end_date with time if needed
                    df_view = df_view.loc[df_view.index <= pd.to_datetime(end_date) + pd.Timedelta(days=1)]

                    # Round numeric columns safely
                    numeric_cols = df_view.select_dtypes(include="number").columns
                    for col in numeric_cols:
                        if str(col).startswith("RSI"):
                            df_view[col] = df_view[col].round(2)
                        else:
                            df_view[col] = df_view[col].round(4)

                    # Save last df for download
                    st.session_state["last_df"] = df_view

                    # Display info: find first/last non-null RSI in the view (should exist if warmup adequate)
                    non_null_idx = df_view.index[df_view[f"RSI_{rsi_period}"].notna()] if f"RSI_{rsi_period}" in df_view.columns else []
                    if len(non_null_idx) > 0:
                        first_idx = non_null_idx[0]
                        last_idx = non_null_idx[-1]
                        range_str = f"{first_idx.strftime('%Y-%m-%d %H:%M')} → {last_idx.strftime('%Y-%m-%d %H:%M')}"
                    else:
                        range_str = "לא מספיק נתונים לחישוב RSI בטווח זה (שקול להגדיל חימום)"

                    st.success(
                        f"נמצאו {len(df_view)} שורות לתצוגה — חישוב RSI על בסיס: {source_used} — טווח RSI: {range_str}"
                    )

                    preview_count = st.slider(
                        "הצג שורות (Preview)",
                        min_value=5,
                        max_value=min(1000, max(5, len(df_view))),
                        value=min(25, max(5, len(df_view))),
                        step=5
                    )
                    st.dataframe(df_view.tail(preview_count), use_container_width=True)

                    with st.expander("הצג גרפים"):
                        if "Close" in df_view.columns:
                            st.line_chart(df_view["Close"].dropna().tail(500))
                        if has_adj and "Adj Close" in df_view.columns:
                            st.line_chart(df_view["Adj Close"].dropna().tail(500))
                        if f"RSI_{rsi_period}" in df_view.columns:
                            st.line_chart(df_view[f"RSI_{rsi_period}"].dropna().tail(500))

                    # Downloads
                    try:
                        csv_bytes = make_csv_bytes(df_view)
                        excel_bytes = make_excel_bytes(df_view)
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
st.caption("הערה: חימום גדול מבטיח ש-RSI של ה'יום הראשון' בטווח יחושב מהיסטוריה ארוכה. עבור אינטרדיי ייתכנו הגבלות מצד Yahoo — האפליקציה תקצר חימום במידת הצורך ותתריע.")
