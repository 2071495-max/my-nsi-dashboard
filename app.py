import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 웹페이지 기본 브라우저 설정
st.set_page_config(page_title="NSI 그물망 매매 대시보드", layout="wide")
st.title("📊 NSI (Net Spread Index) 미국 주식 모니터링 시스템")

# 2. 사이드바 제어 영역 및 한글-티커 매칭 시스템
st.sidebar.header("⚙️ 설정 파라미터")

favorite_stocks = {
    "로켓랩 (RKLB)": "RKLB",
    "엔비디아 (NVDA)": "NVDA",
    "테슬라 (TSLA)": "TSLA",
    "마이크론 (MU)": "MU",
    "팔란티어 (PLTR)": "PLTR",
    "아마존 (AMZN)": "AMZN",
    "알파벳C (GOOG)": "GOOG",
    "AMD (AMD)": "AMD",
    "인텔 (INTC)": "INTC",
    "블룸에너지 (BE)": "BE",
    "아이온큐 (IONQ)": "IONQ",
    "오클로 (OKLO)": "OKLO",
    "아이렌 (IREN)": "IREN",
    "샌디스크/웨스턴디지털 (WDC)": "WDC",
    "QQQ 테크 ETF": "QQQ",
    "VOO S&P500 ETF": "VOO",
    "직접 티커 입력하기": ""
}

selected_korean = st.sidebar.selectbox("🌟 자주 보는 종목 퀵 서치 (한글)", list(favorite_stocks.keys()))
default_ticker = favorite_stocks[selected_korean]

if not default_ticker:
    default_ticker = "RKLB"

ticker = st.sidebar.text_input("미국 주식 티커 입력 (영문 대문자)", value=default_ticker).upper()

st.sidebar.markdown("---")
st.sidebar.subheader("📈 알고리즘 엔진 튜닝")
period = st.sidebar.selectbox("데이터 조회 기간", ["1y", "2y", "5y"], index=0)
nsi_window = st.sidebar.slider("NSI 평균 기준일수 (과열 판단용)", 10, 60, 15)
bb_std = st.sidebar.slider("볼린저 밴드 표준편차 배수", 0.5, 3.0, 1.0, step=0.1)

st.sidebar.markdown("---")
st.sidebar.subheader("🕸️ 그물망 구조 제어")
max_ma = st.sidebar.slider("그물망 최대 장기 이평선 (일)", 30, 200, 40, step=10)
ma_interval = st.sidebar.slider("이평선 간격 (일)", 2, 10, 3)

# 3. 데이터 수집 및 NSI 연산 로직 (안전성 강화 버전)
@st.cache_data(ttl=3600)
def load_and_calc_nsi(ticker, period, nsi_window, bb_std, max_ma, ma_interval):
    # 💡 데이터 개수 부족 에러를 방지하기 위해 period가 1y일 때 내부적으로 여유있게 가져옵니다.
    fetch_period = period
    if period == "1y":
        fetch_period = "2y"
        
    df = yf.download(ticker, period=fetch_period)
    if df.empty:
        return pd.DataFrame()
    
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    df = df.squeeze()
    
    ma_days = list(range(5, max_ma + ma_interval, ma_interval))
    ma_cols = []
    for day in ma_days:
        col_name = f'MA_{day}'
        df[col_name] = df['Close'].rolling(window=day).mean()
        ma_cols.append(col_name)
    
    ma_std = df[ma_cols].std(axis=1)
    df['MA_20'] = df['Close'].rolling(window=20).mean()
    raw_nsi = (ma_std / df['MA_20']) * 100
    
    direction = np.where(df['Close'] >= df['MA_20'], 1, -1)
    df['NSI'] = raw_nsi * direction
    
    df['NSI_MA'] = df['NSI'].rolling(window=nsi_window).mean()
    df['NSI_STD'] = df['NSI'].rolling(window=nsi_window).std()
    df['NSI_Upper'] = df['NSI_MA'] + (bb_std * df['NSI_STD'])
    df['NSI_Lower'] = df['NSI_MA'] - (bb_std * df['NSI_STD'])
    
    df.attrs['ma_cols'] = ma_cols
    
    # dropna 이후 데이터가 완전히 비어버리거나 부족해지는 버그 방어
    df_cleaned = df.dropna()
    
    # 사용자가 원래 요청한 기간(1y 등)만큼만 최종 슬라이싱하여 일관성 유지
    if period == "1y":
        df_cleaned = df_cleaned.tail(252)
        
    return df_cleaned

df = load_and_calc_nsi(ticker, period, nsi_window, bb_std, max_ma, ma_interval)

# 데이터 최소 길이 점검 (최소 22거래일 이상이 확보되어야 오류가 안 남)
if df.empty or len(df) < 25:
    st.error("티커가 유효하지 않거나 분석에 필요한 데이터 개수가 부족합니다. 데이터 조회 기간을 '2y' 이상으로 늘려보세요.")
else:
    ma_cols = df.attrs['ma_cols']
    
    today = df.iloc[-1]
    yesterday = df.iloc[-2]
    two_days_ago = df.iloc[-3]
    
    current_price = float(today['Close'])
    current_nsi = float(today['NSI'])
    upper_bound = float(today['NSI_Upper'])
    lower_bound = float(today['NSI_Lower'])
    
    signal = "⏳ 관망 (추세 유지 중)"
    color = "gray"
    comment = ""
    
    t_nsi = float(today['NSI'])
    y_nsi = float(yesterday['NSI'])
    t2_nsi = float(two_days_ago['NSI'])
    
    buy_cond_A = (y_nsi < float(yesterday['NSI_Lower'])) and (t_nsi > y_nsi)
    buy_cond_B = (t2_nsi < y_nsi < t_nsi) and (y_nsi > 0 or t_nsi > 0) and (t_nsi - y_nsi > 0.5)
    
    sell_cond_A = (y_nsi > float(yesterday['NSI_Upper'])) and (t_nsi < y_nsi)
    sell_cond_B = (t2_nsi > y_nsi > t_nsi) and (t_nsi > 0) and (y_nsi - t_nsi > 0.3)

    if buy_cond_A or buy_cond_B:
        signal = "🔥 매수 타이밍 (그물망 확장 전환 컨펌!)"
        color = "green"
        comment = "역배열 혹은 극도로 축소(수렴)되었던 그물망이 에너지를 모아 위쪽으로 입을 벌리기 시작했습니다. 세력 및 기관의 강한 거래량이 실린 매수세가 유입되는 초입이므로, 적극적인 **매수 포지션**을 고려하기 좋은 타이밍입니다."
    elif sell_cond_A or sell_cond_B:
        signal = "🚨 매도 타이밍 (그물망 피크아웃 컨펌!)"
        color = "red"
        comment = "하늘 높이 벌어지던 정배열 그물망의 확장 탄력이 멈추고 단기 이평선들이 아래로 고개를 숙였습니다. 상승 에너지가 소멸하고 주가가 20일선(평균) 쪽으로 강하게 회귀하려는 변곡점이므로, **수익 실현(청산)**으로 현금을 확보할 타이밍입니다."
    elif (t_nsi < lower_bound) or ((y_nsi < 0) and (t_nsi > y_nsi)):
        signal = "👀 매수 대기 (바닥 탈출 타점 포착)"
        color = "orange"
        comment = "그물망이 바닥권에서 진정세를 보이며 첫 번째 양의 방향성을 틀었습니다. 속임수 반등일 수 있으므로 내일 하루 더 확장이 이어지는지 확인하세요."
    elif (t_nsi > upper_bound) or ((y_nsi > 0) and (t_nsi < y_nsi)):
        signal = "⚠️ 매도 대기 (고점 둔화 타점 포착)"
        color = "magenta"
        comment = "정배열 그물이 극대화된 과열 영역입니다. 오늘 처음으로 상승 각도가 무뎌졌으니 매도 주문창을 켜고 대응할 준비를 시작하세요."
    else:
        if t_nsi >= 0:
            comment = "**🔍 현재 상황:** 주가가 그물망의 탄탄한 정배열 지지를 받으며 안정적인 상승 궤도를 유지 중입니다. \n\n**💡 대응 매뉴얼:** 신호가 완전히 꺾이기 전까지는 기존 물량을 **보유(Hold)**하며 추세를 끝까지 즐기세요."
        else:
            comment = "**🔍 현재 상황:** 주가가 역배열 그물망에 짓눌려 하방 압력을 받고 있습니다. \n\n**💡 대응 매뉴얼:** 수렴 후 위로 튀어 오르는 빅뱅 자리가 나오기 전까지는 안전하게 **관망**을 유지하세요."

    # 5. 대시보드 스코어카드 영역
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(label=f"{ticker} 현재 종가", value=f"${current_price:.2f}")
    col2.metric(label="오늘의 NSI 지수", value=f"{current_nsi:.3f}")
    col3.metric(label="🔴 오늘의 상단 과열선", value=f"{upper_bound:.3f}")
    col4.metric(label="🟢 오늘의 하단 과침체선", value=f"{lower_bound:.3f}")
    
    st.markdown(f"### 현재 신호 상태: <span style='color:{color}'>{signal}</span>", unsafe_allow_html=True)
    st.info(comment)
    st.markdown("---")
    
    # ----------------------------------------------------
    # [과거 20일 신호 복기 데이터프레임 빌드]
    # ----------------------------------------------------
    st.subheader("⏰ 과거 20일간의 매매 신호 추적 및 현재 수익률 복기")
    
    log_df = df.tail(22).copy()
    rows = []
    
    for i in range(2, len(log_df)):
        t_day = log_df.iloc[i]
        y_day = log_df.iloc[i-1]
        t_2_day = log_df.iloc[i-2]
        
        d_nsi = float(t_day['NSI'])
        d_lower = float(t_day['NSI_Lower'])
        d_upper = float(t_day['NSI_Upper'])
        
        d_type = ""
        bg_color = "#ffffff"
        
        d_t_nsi = d_nsi
        d_y_nsi = float(y_day['NSI'])
        d_t2_nsi = float(t_2_day['NSI'])
        
        b_cond_A = (d_y_nsi < float(y_day['NSI_Lower'])) and (d_t_nsi > d_y_nsi)
        b_cond_B = (d_t2_nsi < d_y_nsi < d_t_nsi) and (d_y_nsi > 0 or d_t_nsi > 0) and (d_t_nsi - d_y_nsi > 0.5)
        
        s_cond_A = (d_y_nsi > float(y_day['NSI_Upper'])) and (d_t_nsi < d_y_nsi)
        s_cond_B = (d_t2_nsi > d_y_nsi > d_t_nsi) and (d_t_nsi > 0) and (d_y_nsi - d_t_nsi > 0.3)
        
        if b_cond_A or b_cond_B:
            d_type = "🟢 매수 컨펌"
            bg_color = "#e8f8f5"
        elif s_cond_A or s_cond_B:
            d_type = "🔴 매도 컨펌"
            bg_color = "#fce4d6"
        elif (d_t_nsi < d_lower) or ((d_y_nsi < 0) and (d_t_nsi > d_y_nsi)):
            d_type = "🔸 매수 대기"
            bg_color = "#fef9e7"
        elif (d_t_nsi > d_upper) or ((d_y_nsi > 0) and (d_t_nsi < d_y_nsi)):
            d_type = "🔹 매도 대기"
            bg_color = "#f5eef8"
            
        if d_type != "":
            past_price = float(t_day['Close'])
            rtn = ((current_price - past_price) / past_price) * 100
            
            if "매도" in d_type:
                rtn = ((past_price - current_price) / past_price) * 100
                rtn_label = "하락 방어율"
            else:
                rtn_label = "가상 수익률"
                
            date_str = t_day.name.strftime('%Y-%m-%d')
            target_band = d_upper if "매도" in d_type else d_lower
            
            rows.append({
                "📅 발생 일자": date_str,
                "🚦 신호 구분": d_type,
                "📊 당시 NSI": f"{d_nsi:.3f}",
                "🎯 기준선": f"{target_band:.2f}",
                "💵 당시 주가": f"${past_price:.2f}",
                "📈 현재 성적": f"{rtn_label}: {rtn:+.2f}%",
                "_bg_color": bg_color,
                "_is_positive": bool(rtn >= 0)
            })

    if not rows:
        st.info("📆 최근 20일 동안 시스템에 포착된 매매 신호가 없습니다. 현재 안정적인 추세 유지 구간입니다.")
    else:
        summary_df = pd.DataFrame(list(reversed(rows)))
        
        def apply_row_styles(df_data):
            style_matrix = pd.DataFrame('', index=df_data.index, columns=df_data.columns)
            for i in range(len(df_data)):
                row_bg = df_data.iloc[i]['_bg_color']
                is_pos = df_data.iloc[i]['_is_positive']
                
                style_matrix.iloc[i] = f"background-color: {row_bg};"
                text_color = '#27ae60' if is_pos else '#c0392b'
                style_matrix.iloc[i, style_matrix.columns.get_loc('📈 현재 성적')] = f"background-color: {row_bg}; color: {text_color}; font-weight: bold;"
                
            return style_matrix

        final_styler = summary_df.style.apply(apply_row_styles, axis=None) \
            .hide(axis="index") \
            .hide(subset=["_bg_color", "_is_positive"], axis="columns")

        st.dataframe(final_styler, use_container_width=True, on_select="ignore")

    st.markdown("---")
    
    # 6. Plotly 고해상도 차트 구현
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.6, 0.4])
    fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='Close', line=dict(color='black', width=2.5)), row=1, col=1)
    
    for col in ma_cols:
        is_ma20 = (col == 'MA_20')
        width = 2.5 if is_ma20 else 0.7
        color_code = 'rgba(255, 127, 14, 0.9)' if is_ma20 else 'rgba(180, 180, 180, 0.35)'
        fig.add_trace(go.Scatter(x=df.index, y=df[col], name=col, line=dict(color=color_code, width=width)), row=1, col=1)
        
    fig.add_trace(go.Scatter(x=df.index, y=df['NSI'], name='NSI 지수', line=dict(color='#1f77b4', width=1.8)), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['NSI_Upper'], name='상단 과열선', line=dict(color='#d62728', width=1.2, dash='dash')), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['NSI_Lower'], name='하단 과침체선', line=dict(color='#2ca02c', width=1.2, dash='dash')), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['NSI_MA'], name='NSI 중심선', line=dict(color='rgba(100,100,100,0.5)', width=0.8)), row=2, col=1)
    
    fig.update_layout(height=700, margin=dict(l=50, r=50, b=50, t=30), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)
