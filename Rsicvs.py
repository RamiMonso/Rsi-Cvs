# app.py - Streamlit app: Yahoo Finance → Close + RSI(14)
# העתק/הדבק והריץ (streamlit run app.py)
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
    # Wilder smoothing via EWM
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

@st.cache_data(show_spinner=False)
def download_data(ticker: str, start: date, end: date, interval: str) -> pd.DataFrame:
    # הוספת יום ל-end כדי לכלול את יום הסיום בבקשות יומיות
    df = yf.download(
        ticker,
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        interval=interval,
        progress=False,
        threads=True,
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
st.title("Yahoo Finance — Close + RSI(14)")
st.markdown(
    "הכנס טיקר, טווח תאריכים ובחר גרף (יומי/שעה). התוצאה: טבלת `Close` ו-`RSI(14)` לכל נר + כפתורי הורדה ל-CSV/Excel."
)

left_col, right_col = st.columns([1, 2])

# ---------- Left column: form ----------
with left_col:
    st.header("הגדרות חיפוש")
    example_fill = st.button("מלא דוגמה (AAPL, 30 יום אחרונים)")

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
                value=st.session_state.get("start_date", date.today() - timedelta(days=30))
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
        include_ohlcv = st.checkbox(
            "הצג עמודות נוספות (Open/High/Low/Volume)",
            value=st.session_state.get("include_ohlcv", False)
        )
        submit = st.form_submit_button("הורד והצג")

    if example_fill:
        # ממלא דוגמה וגורם להרצה מחדש לקבלת הערכים
        st.session_state["ticker"] = "AAPL"
        st.session_state["start_date"] = date.today() - timedelta(days=30)
        st.session_state["end_date"] = date.today()
        st.session_state["interval_choice"] = "יומי (Daily)"
        st.session_state["rsi_period"] = 14
        st.session_state["include_ohlcv"] = False
        st.experimental_rerun()

    if submit:
        # שמירת ערכים בסשן לשימוש בעמוד התוצאות
        st.session_state["ticker"] = ticker.strip().upper()
        st.session_state["start_date"] = start_date
        st.session_state["end_date"] = end_date
        st.session_state["interval_choice"] = interval_choice
        st.session_state["rsi_period"] = int(rsi_period)
        st.session_state["include_ohlcv"] = include_ohlcv

    st.markdown("---")
    st.write("טיפים:")
    st.write("- אם אין נתונים עבור 'שעה' — נסה טווח קצר יותר (למשל 7-30 ימים).")
    st.write("- התחילו עם טיקרים ידועים (AAPL, MSFT) כדי לבדוק תקינות.")

# ---------- Right column: results / status ----------
with right_col:
    st.header("תוצאות")
    has_input = all(k in st.session_state for k in ("ticker", "start_date", "end_date", "interval_choice", "rsi_period"))
    if not has_input:
        st.info("מלא את הפרטים משמאל ולחץ 'הורד והצג' כדי להתחיל.")
    else:
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

                # בחירת עמודות להצגה
                cols_to_keep = ["Close"]
                if include_ohlcv:
                    for c in ("Open", "High", "Low", "Volume"):
                        if c in df.columns:
                            cols_to_keep.insert(0, c)
                df_res = df[cols_to_keep].copy()
                df_res.index.name = "Datetime"

                # חישוב RSI
                df_res[f"RSI_{rsi_period}"] = compute_rsi(df_res["Close"], period=rsi_period)

                # ======= תיקן את הבעיה כאן: ודא שהשם הוא מחרוזת לפני startswith =======
                numeric_cols = df_res.select_dtypes(include="number").columns
                for col in numeric_cols:
                    # המרת שם העמודה ל-str לפני בדיקת startswith — מונעת AttributeError
                    if str(col).startswith("RSI"):
                        df_res[col] = df_res[col].round(2)
                    else:
                        df_res[col] = df_res[col].round(4)
                # ======================================================================

                # שמירת התוצאה בסשן לשימוש ב-download
                st.session_state["last_df"] = df_res

                # הצגת סיכום וטבלת דוגמה
                st.success(
                    f"נמצאו {len(df_res)} שורות — טווח: "
                    f"{df_res.index[0].strftime('%Y-%m-%d %H:%M')} → {df_res.index[-1].strftime('%Y-%m-%d %H:%M')}"
                )

                preview_count = st.slider(
                    "הצג שורות (Preview)",
                    min_value=5,
                    max_value=min(1000, len(df_res)),
                    value=min(25, len(df_res)),
                    step=5
                )
                st.dataframe(df_res.tail(preview_count), use_container_width=True)

                # גרפים בתוך expander
                with st.expander("הצג גרפים"):
                    st.line_chart(df_res["Close"].tail(500))
                    st.line_chart(df_res[f"RSI_{rsi_period}"].tail(500))

                # לחצני הורדה
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

# ---------- Footer ----------
st.markdown("***")
st.caption("הערה: נתוני 'שעה' עשויים להיות מוגבלים על ידי Yahoo Finance. אם תרצה — אני מוסיף בדיקה שתמנע בקשות לטווחים ארוכים עבור אינטרדיי.")
