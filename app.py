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
    "직접 티커 입력하기": "",
    "로켓랩 (RKLB)": "RKLB",
    "테슬라 (TSLA)": "TSLA",
    "엔비디아 (NVDA)": "NVDA",
    "마이크론 (MU)": "MU",
    "팔란티어 (PLTR)": "PLTR",
    "아마zon (AMZN)": "AMZN",
    "알파벳C (GOOG)": "GOOG",
    "AMD (AMD)": "AMD",
    "인텔 (INTC)": "INTC",
    "블룸에너지 (BE)": "BE",
    "아이온큐 (IONQ)": "IONQ",
    "오클로 (OKLO)": "OKLO",
    "아이렌 (IREN)": "IREN",
    "샌디스크/웨스턴디지털 (WDC)": "WDC",
    "QQQ 테크 ETF": "QQQ",
    "VOO S&P500 ETF": "VOO"
}

selected_korean = st.sidebar.selectbox("🌟 자주 보는 종목 퀵 서치 (한글)", list(favorite_stocks.keys()))
default_ticker = favorite_stocks[selected_korean]

ticker = st.sidebar.text_input("미국 주식 티커 입력 (영문 대문자)", value=default_ticker if default_ticker else "RKLB").upper()

st.sidebar.markdown("---")
st.sidebar.subheader("📈 알고리즘 엔진 튜닝 (로켓랩 맞춤 세팅 권장)")
period = st.sidebar.selectbox("데이터 조회 기간", ["1y", "2y", "5y"], index=0)
nsi_window = st.sidebar.slider("NSI 평균 기준일수 (과열 판단용)", 10, 60, 15)  # 20 -> 15로 민감도 상향
bb_std = st.sidebar.slider("볼린저 밴드 표준편차 배수", 0.5, 3.0, 1.0, step=0.1)    # 1.5 -> 1.0으로 밴드 좁힘

st.sidebar.markdown("---")
st.sidebar.subheader("🕸️ 그물망 구조 제어")
max_ma = st.sidebar.slider("그물망 최대 장기 이평선 (일)", 30, 200, 40, step=10)   # 60 -> 40으로 단기 추세 민감화
ma_interval = st.sidebar.slider("이평선 간격 (일)", 2, 10, 3)                     # 5 -> 3으로 더 촘촘하게

# 3. 데이터 수집 및 NSI 연산 로직
@st.cache_data(ttl=3600)
def load_and_calc_nsi(ticker, period, nsi_window, bb_std, max_ma, ma_interval):
    df = yf.download(ticker, period=period)
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
    return df.dropna()

df = load_and_calc_nsi(ticker, period, nsi_window, bb_std, max_ma, ma_interval)

if df.empty:
    st.error("티커가 유효하지 않거나 주가 데이터를 불러올 수 없습니다. 사이드바의 영문 티커 스펠링을 확인해 주세요.")
else:
    ma_cols = df.attrs['ma_cols']
    
    # 최근 3일 데이터 추출
    today = df.iloc[-1]
    yesterday = df.iloc[-2]
    two_days_ago = df.iloc[-3]
    
    current_price = float(today['Close'])
    current_nsi = float(today['NSI'])
    upper_bound = float(today['NSI_Upper'])
    lower_bound = float(today['NSI_Lower'])
    
    # ----------------------------------------------------
    # 🆕 [로켓랩 타점 맞춤형 업그레이드 신호 엔진]
    # ----------------------------------------------------
    signal = "⏳ 관망 (추세 유지 중)"
    color = "gray"
    comment = ""
    
    # 핵심 판정 변수들 생성
    t_nsi = float(today['NSI'])
    y_nsi = float(yesterday['NSI'])
    t2_nsi = float(two_days_ago['NSI'])
    
    # 1. 매수 조건 (수렴 후 확산 초입 포착)
    # 조건 A: 기존 밴드 하단 돌파 후 반등 패턴
    buy_cond_A = (y_nsi < float(yesterday['NSI_Lower'])) and (t_nsi > y_nsi)
    # 조건 B: 그물망이 수렴(0 근처)했다가 20일선 위로 고개를 들며 강하게 확장하기 시작하는 빅뱅 초입 (질문자님 차트의 핵심 타점)
    buy_cond_B = (t2_nsi < y_nsi < t_nsi) and (y_nsi > 0 or t_nsi > 0) and (t_nsi - y_nsi > 0.5)
    
    # 2. 매도 조건 (정배열 확산 후 피크아웃 초입 포착)
    # 조건 A: 기존 밴드 상단 돌파 후 꺾임 패턴
    sell_cond_A = (y_nsi > float(yesterday['NSI_Upper'])) and (t_nsi < y_nsi)
    # 조건 B: 그물망이 위로 쫙 벌어지며 고점을 찍은 후, 이틀 연속 두께가 수축하기 시작하는 시점 (피크아웃 어깨 타점)
    sell_cond_B = (t2_nsi > y_nsi > t_nsi) and (t_nsi > 0) and (y_nsi - t_nsi > 0.3)

    if buy_cond_A or buy_cond_B:
        signal = "🔥 매수 타이밍 (그물망 확장 전환 컨펌!)"
        color = "green"
        comment = "역배열 혹은 극도로 축소(수렴)되었던 그물망이 에너지를 모아 위쪽으로 입을 벌리기 시작했습니다. 세력 및 기관의 강한 거래량이 실린 매수세가 유입되는 초입 기차이므로, 적극적인 **매수 포지션**을 고려하기 좋은 타이밍입니다."
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
    # [과거 20일 신호 복기 및 백트래킹 로그 데이터프레임 빌드]
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
        style_key = "normal"
        
        # 과거 루프 내에서도 동일한 민감 알고리즘 적용
        d_t_nsi = d_nsi
        d_y_nsi = float(y_day['NSI'])
        d_t2_nsi = float(t_2_day['NSI'])
        
        b_cond_A = (d_y_nsi < float(y_day['NSI_Lower'])) and (d_t_nsi > d_y_nsi)
        b_cond_B = (d_t2_nsi < d_y_nsi < d_t_nsi) and (d_y_nsi > 0 or d_t_nsi > 0) and (d_t_nsi - d_y_nsi > 0.5)
        
        s_cond_A = (d_y_nsi > float(y_day['NSI_Upper'])) and (d_t_nsi < d_y_nsi)
        s_cond_B = (d_t2_nsi > d_y_nsi > d_t_nsi) and (d_t_nsi > 0) and (d_y_nsi - d_t_nsi > 0.3)
        
        if b_cond_A or b_cond_B:
            d_type = "🟢 매수 컨펌"
            style_key = "bold_buy"
        elif s_cond_A or s_cond_B:
            d_type = "🔴 매도 컨펌"
            style_key = "bold_sell"
        elif (d_t_nsi < d_lower) or ((d_y_nsi < 0) and (d_t_nsi > d_y_nsi)):
            d_type = "🔸 매수 대기"
            style_key = "wait_buy"
        elif (d_t_nsi > d_upper) or ((d_y_nsi > 0) and (d_t_nsi < d_y_nsi)):
            d_type = "🔹 매도 대기"
            style_key = "wait_sell"
            
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
                "📊 당시 NSI": round(d_nsi, 3),
                "🎯 기준선": round(target_band, 2),
                "💵 당시 주가": f"${past_price:.2f}",
                "📈 현재 성적": rtn,
                "rtn_label": rtn_label,
                "style_key": style_key
            })

    if not rows:
        st.write("📆 최근 20일 동안 새로운 필터 기반의 매매 신호가 잡히지 않았습니다.")
    else:
        summary_df = pd.DataFrame(list(reversed(rows)))
        
        # 순정 Pandas Styler 엔진 매핑
        def style_rows(row):
            bg_colors = {
                "bold_buy": "background-color: #e8f8f5;",
                "bold_sell": "background-color: #fce4d6;",
                "wait_buy": "background-color: #fef9e7;",
                "wait_sell": "background-color: #f5eef8;"
            }
            color = bg_colors.get(row['style_key'], "background-color: #ffffff;")
            return [color] * len(row)

        def format_rtn(val, df_ctx, idx):
            label = df_ctx.loc[idx, 'rtn_label']
            return f"{label}: {val:+.2f}%"

        def color_rtn(val):
            color = "#27ae60" if val >= 0 else "#c0392b"
            return f"color: {color}; font-weight: bold;"

        formatted_dict = {}
        for idx, row in summary_df.iterrows():
            formatted_dict[idx] = format_rtn(row['📈 현재 성적'], summary_df, idx)

        styler = summary_df.style.apply(style_rows, axis=1) \
            .applymap(color_rtn, subset=["📈 현재 성적"]) \
            .format(formatter=formatted_dict, subset=["📈 현재 성적"]) \
            .hide(axis="index") \
            .hide(subset=["rtn_label", "style_key"], axis="columns")

        st.dataframe(styler, use_container_width=True)

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
