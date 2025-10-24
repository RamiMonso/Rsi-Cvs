import streamlit as st
import pandas as pd
import yfinance as yf
import ta

st.title("📊 הורדת נתוני סגירה ו-RSI מהבורסה האמריקאית")

# הזנת פרטי המשתמש
ticker = st.text_input("הזן טיקר (לדוגמה: AAPL, MSFT, TSLA):").upper()
period = st.selectbox("בחר תקופה:", ["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"])
interval = st.selectbox("בחר סוג גרף:", ["1h", "1d"], format_func=lambda x: "שעתי" if x == "1h" else "יומי")

if st.button("📥 הורד נתונים"):
    if not ticker:
        st.error("אנא הזן טיקר תקין.")
    else:
        try:
            with st.spinner("מוריד נתונים..."):
                df = yf.download(ticker, period=period, interval=interval)
            
            if df.empty:
                st.error("לא נמצאו נתונים לטיקר או לטווח שבחרת.")
            else:
                # איפוס אינדקס והבטחת קיומה של עמודת תאריך
                df_reset = df.reset_index()

                # חיפוש עמודת זמן / תאריך
                datetime_col = None
                for c in df_reset.columns:
                    if "date" in str(c).lower() or "time" in str(c).lower():
                        datetime_col = c
                        break

                if datetime_col is None:
                    raise KeyError("לא נמצאה עמודת תאריך/זמן בנתונים שהורדו.")

                # חישוב RSI (14)
                df_reset["RSI_14"] = ta.momentum.RSIIndicator(df_reset["Close"], window=14).rsi()

                # שמירה של עמודות נדרשות
                output_df = df_reset[[datetime_col, "Close", "RSI_14"]].copy()
                output_df.rename(columns={datetime_col: "Datetime"}, inplace=True)

                # המרה לפורמט קריא
                output_df["Datetime"] = pd.to_datetime(output_df["Datetime"]).dt.strftime("%Y-%m-%d %H:%M:%S")

                # שמירה כקובץ CSV
                csv = output_df.to_csv(index=False).encode("utf-8")
                st.success("✅ הנתונים חושבו בהצלחה!")
                st.download_button(
                    label="⬇️ הורד קובץ CSV",
                    data=csv,
                    file_name=f"{ticker}_RSI_data.csv",
                    mime="text/csv",
                )

                st.dataframe(output_df.tail(20))

        except Exception as e:
            st.error(f"שגיאה: {e}")
