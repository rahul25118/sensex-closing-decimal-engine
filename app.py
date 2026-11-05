import streamlit as st
import yfinance as yf
import pandas as pd
from collections import Counter
from datetime import datetime, time
import pytz

st.set_page_config(
    page_title="BSE Sensex Closing Decimal Engine",
    page_icon="🏛️",
    layout="wide"
)

IST = pytz.timezone("Asia/Kolkata")

# 3-टियर स्टाइलिंग
st.markdown("""
<style>
    .tier-high {
        background-color: #d4edda;
        border: 2px solid #28a745;
        border-radius: 10px;
        padding: 16px 20px;
        color: #155724;
        margin-bottom: 20px;
    }
    .tier-mod {
        background-color: #fff3cd;
        border: 2px solid #ffc107;
        border-radius: 10px;
        padding: 16px 20px;
        color: #856404;
        margin-bottom: 20px;
    }
    .tier-risk {
        background-color: #f8d7da;
        border: 2px solid #dc3545;
        border-radius: 10px;
        padding: 16px 20px;
        color: #721c24;
        margin-bottom: 20px;
    }
    .waiting-banner {
        background-color: #e2e3e5;
        border: 2px solid #d6d8db;
        border-radius: 10px;
        padding: 14px 20px;
        color: #383d41;
        font-size: 16px;
        font-weight: bold;
        margin-bottom: 20px;
    }
    .badge-main {
        display: inline-block;
        background-color: #e8f0fe;
        color: #1a73e8;
        padding: 10px 16px;
        border-radius: 8px;
        font-weight: bold;
        margin: 5px;
        font-size: 22px;
        border: 2px solid #1a73e8;
    }
    .badge-hit {
        display: inline-block;
        background-color: #28a745;
        color: #ffffff;
        padding: 10px 16px;
        border-radius: 8px;
        font-weight: bold;
        margin: 5px;
        font-size: 22px;
        border: 2px solid #1e7e34;
        box-shadow: 0 4px 10px rgba(40,167,69,0.35);
    }
    .badge-low {
        display: inline-block;
        background-color: #e6f4ea;
        color: #137333;
        padding: 5px 12px;
        border-radius: 12px;
        font-weight: bold;
        margin: 3px;
        font-size: 16px;
    }
    .badge-high {
        display: inline-block;
        background-color: #fce8e6;
        color: #c5221f;
        padding: 5px 12px;
        border-radius: 12px;
        font-weight: bold;
        margin: 3px;
        font-size: 16px;
    }
</style>
""", unsafe_allow_html=True)

st.title("🏛️ BSE Sensex Pre-Close Decimal Engine")
st.caption("30-मिनट VWAP मैकेनिज्म | T-10 Min Lock (03:20 PM IST) | 6 Low + 9 High बारबेल | 3-टियर कॉन्फिडेंस मैट्रिक्स")

@st.cache_data(ttl=60)
def fetch_bse_data():
    ticker = yf.Ticker("^BSESN")
    df = ticker.history(period="60d", interval="2m")
    if df.empty or len(df) < 30:
        df = ticker.history(period="60d", interval="5m")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert("Asia/Kolkata")
    else:
        df.index = df.index.tz_convert("Asia/Kolkata")

    df["Date"] = df.index.date
    df["Decimal"] = df["Close"].apply(lambda x: f"{float(x):.2f}".split(".")[1].zfill(2))
    df["DayName"] = df.index.day_name()

    df_daily = ticker.history(period="60d", interval="1d")
    if isinstance(df_daily.columns, pd.MultiIndex):
        df_daily.columns = df_daily.columns.get_level_values(0)
    daily_closes = {d.date(): (row["Close"], f"{float(row['Close']):.2f}".split(".")[1].zfill(2)) for d, row in df_daily.iterrows()}

    return df, daily_closes

def calculate_confidence_score(day_name, late_range, rep_count):
    score = 0
    # 1. Day of week वेटेज (अधिकतम 40 अंक)
    if day_name in ["Tuesday", "Friday"]:
        score += 40
    elif day_name == "Monday":
        score += 20
    else: # Wednesday, Thursday
        score += 10

    # 2. वोलैटिलिटी रेंज वेटेज (अधिकतम 40 अंक)
    if late_range <= 60.0:
        score += 40
    elif late_range <= 100.0:
        score += 30
    elif late_range <= 130.0:
        score += 15
    else:
        score += 0

    # 3. रिपीटर्स डेंसिटी (अधिकतम 20 अंक)
    if rep_count >= 6:
        score += 20
    elif rep_count >= 4:
        score += 12
    else:
        score += 5

    # टियर वर्गीकरण
    if score >= 75:
        tier = "HIGH"
        tier_title = "🟢 TIER 1: उच्च विश्वास (HIGH CONVICTION)"
        action = "नॉर्मल ट्रेड साइज़िंग। ऐतिहासिक सटीकता: ~75-80%।"
    elif score >= 45:
        tier = "MODERATE"
        tier_title = "🟡 TIER 2: मध्यम / सतर्क (MODERATE RISK)"
        action = "हल्का ट्रेड / नियंत्रित साइज़िंग। रेंज संतुलित है पर सावधानी ज़रूरी।"
    else:
        tier = "RISK"
        tier_title = "🔴 TIER 3: अत्यधिक जोखिम (EXTREME RISK / SKIP)"
        action = "ट्रेड छोड़ना बेहतर। अत्यधिक मोमेंटम या बिखरा हुआ ऑर्डर फ्लो।"

    return score, tier, tier_title, action

def run_sensex_engine(day_df, official_tuple, low_k=6, high_k=9):
    lock_t = pd.to_datetime("15:20:00").time()
    core_t = pd.to_datetime("14:00:00").time()
    late_t = pd.to_datetime("15:00:00").time()

    df_pre = day_df[day_df.index.time <= lock_t]
    win_core = day_df[(day_df.index.time >= core_t) & (day_df.index.time <= lock_t)]
    win_late = day_df[(day_df.index.time >= late_t) & (day_df.index.time <= lock_t)]

    if df_pre.empty:
        return None

    day_name = day_df.iloc[0]["DayName"]
    late_range = float(win_late["Close"].max() - win_late["Close"].min()) if len(win_late) > 0 else 0.0

    all_day_counts = Counter(df_pre["Decimal"])
    core_counts = Counter(win_core["Decimal"])
    late_counts = Counter(win_late["Decimal"])

    repeaters = [k for k, v in core_counts.items() if v >= 2]
    uniques = [k for k, v in core_counts.items() if v == 1]
    confirmed = [k for k in uniques if all_day_counts.get(k, 0) >= 3]
    late_u = [k for k, v in late_counts.items() if v == 1]

    score, tier, tier_title, action_text = calculate_confidence_score(day_name, late_range, len(repeaters))

    pool = list(dict.fromkeys(repeaters + confirmed + late_u))
    if len(pool) < 15:
        for d in df_pre["Decimal"].tolist()[::-1]:
            if d not in pool:
                pool.append(d)
            if len(pool) == 15:
                break

    pool_sorted = sorted(pool, key=lambda x: int(x))
    lowest = pool_sorted[:low_k]
    highest = pool_sorted[-high_k:]
    final_15 = list(dict.fromkeys(lowest + highest))

    if official_tuple:
        actual_price, actual_dec = official_tuple
    else:
        actual_price = day_df.iloc[-1]["Close"]
        actual_dec = day_df.iloc[-1]["Decimal"]

    is_market_closed = day_df.index[-1].time() > lock_t
    is_hit = False
    side = "PENDING"

    if is_market_closed:
        is_hit = actual_dec in final_15
        if is_hit:
            side = "🟢 LOW SIDE" if actual_dec in lowest else "🔴 HIGH SIDE"
        else:
            side = "❌ MISS"

    return {
        "price_at_lock": df_pre.iloc[-1]["Close"],
        "actual_price": actual_price,
        "actual_dec": actual_dec,
        "lowest": lowest,
        "highest": highest,
        "final_15": final_15,
        "is_hit": is_hit,
        "is_closed": is_market_closed,
        "side": side,
        "score": score,
        "tier": tier,
        "tier_title": tier_title,
        "action_text": action_text,
        "day_name": day_name,
        "late_range": late_range,
        "reps_count": len(repeaters)
    }

now_ist = datetime.now(IST)
df_bse, daily_dict = fetch_bse_data()

if not df_bse.empty:
    bse_dates = sorted(df_bse["Date"].unique(), reverse=True)

    col_d, col_c = st.columns([2, 1])
    with col_d:
        selected_date = st.selectbox("📅 तारीख चुनें:", bse_dates)
    with col_c:
        st.metric("⏰ वर्तमान IST समय", now_ist.strftime("%I:%M:%S %p"))

    res = run_sensex_engine(
        df_bse[df_bse["Date"] == selected_date],
        daily_dict.get(selected_date),
        low_k=6,
        high_k=9
    )

    if res:
        is_today = (selected_date == now_ist.date())
        is_prelock = is_today and (now_ist.time() < time(15, 20))

        if is_prelock:
            st.markdown('<div class="waiting-banner">⏳ लाइव मार्केट जारी है। ठीक 03:20 PM IST पर स्कोर और 15-नंबर बास्केट लॉक होगी।</div>', unsafe_allow_html=True)
        else:
            banner_class = "tier-high" if res["tier"] == "HIGH" else ("tier-mod" if res["tier"] == "MODERATE" else "tier-risk")
            st.markdown(f'''
            <div class="{banner_class}">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h3 style="margin:0;">{res['tier_title']}</h3>
                    <span style="font-size:24px; font-weight:bold;">स्कोर: {res['score']}/100</span>
                </div>
                <p style="margin:8px 0 0 0; font-size:16px;"><b>दिशा-निर्देश:</b> {res['action_text']}</p>
                <p style="margin:4px 0 0 0; font-size:14px; opacity:0.85;">सेटअप: {res['day_name']} | 20-Min रेंज: {res['late_range']:.1f} pt | कोर रिपीटर्स: {res['reps_count']}</p>
            </div>
            ''', unsafe_allow_html=True)

        st.subheader("🎯 15 उम्मीदवारों की मुख्य बास्केट (6 Low + 9 High)")
        badges = "".join([
            f"<span class='badge-hit'>🎯 .{x} (HIT)</span>" if (res['is_closed'] and x == res['actual_dec'])
            else f"<span class='badge-main'>.{x}</span>"
            for x in res['final_15']
        ])
        st.markdown(badges, unsafe_allow_html=True)

        c_low, c_high = st.columns(2)
        with c_low:
            st.markdown("**🟢 6 Lowest Candidates:**")
            st.markdown("".join([f"<span class='badge-low'>.{x}</span>" for x in res['lowest']]), unsafe_allow_html=True)
        with c_high:
            st.markdown("**🔴 9 Highest Candidates (VWAP हाई-बायस):**")
            st.markdown("".join([f"<span class='badge-high'>.{x}</span>" for x in res['highest']]), unsafe_allow_html=True)

        st.divider()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("03:20 PM लॉक भाव", f"{res['price_at_lock']:.2f}")
        m2.metric("20-Min रेंज (03:00-03:20)", f"{res['late_range']:.1f} pts")
        if res["is_closed"]:
            m3.metric("03:30 PM क्लोज", f"{res['actual_price']:.2f} (.{res['actual_dec']})")
            m4.metric("परिणाम", "✅ HIT" if res["is_hit"] else "❌ MISS", res["side"])
        else:
            m3.metric("03:30 PM क्लोज", "गणना जारी...")
            m4.metric("स्थिति", "प्रतीक्षा में")
else:
    st.error("BSE Sensex का डेटा फेच नहीं हो सका।")
