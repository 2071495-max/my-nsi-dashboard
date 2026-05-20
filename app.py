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
    "테슬라 (TSLA)": "TSLA",
    "엔비디아 (NVDA)": "NVDA",
    "마이크론 (MU)": "MU",
    "아마zon (AMZN)": "AMZN",
    "알파벳C (GOOG)": "GOOG",
    "팔란티어 (PLTR)": "PLTR",
    "AMD (AMD)": "AMD",
    "인텔 (INTC)": "INTC",
    "로켓랩 (RKLB)": "RKLB",
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

ticker = st.sidebar.text_input("미국 주식 티커 입력 (영문 대문자)", value=default_ticker if default_ticker else "TSLA").upper()

st.sidebar.markdown("---")
st.sidebar.subheader("📈 알고리즘 엔진 튜닝")
period = st.sidebar.selectbox("데이터 조회 기간", ["1y", "2y", "5y"], index=0)
nsi_window = st.sidebar.slider("NSI 평균 기준일수 (과열 판단용)", 10, 60, 20)
bb_std = st.sidebar.slider("볼린저 밴드 표준편차 배수", 1.0, 3.0, 1.5, step=0.1)

st.sidebar.markdown("---")
st.sidebar.subheader("🕸️ 그물망 구조 제어")
max_ma = st.sidebar.slider("그물망 최대 장기 이평선 (일)", 40, 200, 60, step=10)
ma_interval = st.sidebar.slider("이평선 간격 (일)", 2, 10, 5)

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
    
    was_buy_day1 = (float(yesterday['NSI']) < float(yesterday['NSI_Lower'])) and (float(yesterday['NSI']) > float(two_days_ago['NSI']))
    is_buy_day2 = current_nsi > float(yesterday['NSI'])
    
    was_sell_day1 = (float(yesterday['NSI']) > float(yesterday['NSI_Upper'])) and (float(yesterday['NSI']) < float(two_days_ago['NSI']))
    is_sell_day2 = current_nsi < float(yesterday['NSI'])
    
    if was_buy_day1 and is_buy_day2:
        signal = "🔥 매수 타이밍 (2일 연속 반등 컨펌!)"
        color = "green"
        comment = "역배열로 넓게 찢어지던 그물망이 이틀 연속 좁혀졌습니다. 시장의 과도한 공포가 진정되고 바닥권에서 신뢰도 높은 저가 매수세가 유입되며 추세가 진짜로 돌아서기 시작했다는 강력한 증거입니다. \n\n**💡 대응 매뉴얼:** 본격적인 매수를 검토할 최적의 타이밍입니다."
    elif was_sell_day1 and is_sell_day2:
        signal = "🚨 매도 타이밍 (2일 연속 꺾임 컨펌!)"
        color = "red"
        comment = "정배열 그물망이 극도로 벌어지며 상승 에너지가 이틀 연속으로 둔화되었습니다. 단기 차익 실현 물량이 대거 쏟아지고 있으며, 주가가 20일선(평균)으로 회귀하려는 인력이 작용하고 있습니다. \n\n**💡 대응 매뉴얼:** 안전하게 수익을 확실히 챙겨야(청산) 하는 구간입니다."
    elif (current_nsi < lower_bound) and (current_nsi > float(yesterday['NSI'])):
        signal = "👀 매수 대기 (반등 1일 차)"
        color = "orange"
        comment = "밑으로 쫙 펼쳐져 있던 하락 그물망이 오늘 처음으로 살짝 좁혀졌습니다. 낙폭과대에 따른 일시적인 기술적 반등일 가능성이 있으므로 내일까지 지켜보는 것이 안전합니다."
    elif (current_nsi > upper_bound) and (current_nsi < float(yesterday['NSI'])):
        signal = "⚠️ 매도 대기 (고점 1일 차)"
        color = "magenta"
        comment = "그물망이 역대급으로 벌어지며 과매수 영역의 정점을 찍고 오늘 처음으로 꺾였습니다. 단기 상승 피로감이 한계에 달한 상태이므로 슬슬 매도 주문을 준비해야 합니다."
    else:
        if current_nsi >= 0:
            comment = "**🔍 현재 상황:** 주가가 20일선 위에서 그물망의 탄탄한 지지를 받으며 안정적인 상승 흐름을 유지하고 있습니다. \n\n**💡 대응 매뉴얼:** 추세를 즐기며 기존 물량을 편안하게 **보유(Hold)**하세요."
        else:
            comment = "**🔍 현재 상황:** 주가가 20일선 아래에서 역배열 그물망에 무겁게 짓눌려 하락 터널을 지나고 있습니다. \n\n**💡 대응 매뉴얼:** 바닥이 어디인지 알 수 없는 구간이므로 철저히 **관망**을 유지해야 합니다."

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
    # [과거 20일 신호 복기 및 수익률 백트래킹 로그 + 표 구조화]
    # ----------------------------------------------------
    st.subheader("⏰ 과거 20일간의 매매 신호 추적 및 현재 수익률 복기")
    
    log_df = df.tail(22).copy()
    log_list = []
    
    for i in range(2, len(log_df)):
        t_day = log_df.iloc[i]
        y_day = log_df.iloc[i-1]
        t_2_day = log_df.iloc[i-2]
        
        d_nsi = float(t_day['NSI'])
        d_lower = float(t_day['NSI_Lower'])
        d_upper = float(t_day['NSI_Upper'])
        
        d_type = ""
        d_style = "normal" 
        
        w_buy1 = (float(y_day['NSI']) < float(y_day['NSI_Lower'])) and (float(y_day['NSI']) > float(t_2_day['NSI']))
        i_buy2 = d_nsi > float(y_day['NSI'])
        
        w_sell1 = (float(y_day['NSI']) > float(y_day['NSI_Upper'])) and (float(y_day['NSI']) < float(t_2_day['NSI']))
        i_sell2 = d_nsi < float(y_day['NSI'])
        
        if w_buy1 and i_buy2:
            d_type = "🟩 매수 컨펌 (2일차)"
            d_style = "bold_buy"
        elif w_sell1 and i_sell2:
            d_type = "🟥 매도 컨펌 (2일차)"
            d_style = "bold_sell"
        elif (d_nsi < d_lower) and (d_nsi > float(y_day['NSI'])):
            d_type = "🟧 매수 대기 (1일차)"
            d_style = "wait_buy"
        elif (d_nsi > d_upper) and (d_nsi < float(y_day['NSI'])):
            d_type = "🟪 매도 대기 (1일차)"
            d_style = "wait_sell"
            
        if d_type != "":
            past_price = float(t_day['Close'])
            rtn = ((current_price - past_price) / past_price) * 100
            
            if "매도" in d_type:
                rtn = ((past_price - current_price) / past_price) * 100
                rtn_label = "하락 방어율"
            else:
                rtn_label = "가상 수익률"
                
            date_str = t_day.name.strftime('%Y-%m-%d')
            log_list.append({
                'date': date_str, 'type': d_type, 'price': past_price, 
                'nsi': d_nsi, 'upper': d_upper, 'lower': d_lower, 'rtn': rtn, 'rtn_label': rtn_label, 'style': d_style
            })

    if not log_list:
        st.write("📆 최근 20일 동안 발생한 특이 매수/매도 신호가 없습니다. 평온한 추세 구간입니다.")
    else:
        # 🆕 [해결 가이드] 태그 내부 인라인 스타일 차단을 우회하기 위해 글로벌 스타일시트(CSS) 분리 선언
        css_style = """
        <style>
            .nsi-table { width: 100% !important; border-collapse: collapse !important; border: 2px solid #4b5563 !important; font-family: sans-serif !important; margin-bottom: 25px; background-color: #ffffff; }
            .nsi-table th { background-color: #e5e7eb !important; border: 1px solid #9ca3af !important; padding: 12px 10px !important; color: #111827 !important; text-align: center !important; font-weight: bold !important; }
            .nsi-table td { border: 1px solid #d1d5db !important; padding: 12px 10px !important; color: #111827 !important; }
            .text-center { text-align: center !important; }
            .text-left { text-align: left !important; }
            .text-right { text-align: right !important; }
            .font-bold { font-weight: bold !important; }
            
            /* 신호별 테마 클래스 지정 */
            .row-normal { background-color: #ffffff !important; }
            .row-bold_buy { background-color: #e8f8f5 !important; font-weight: bold !important; }
            .row-bold_sell { background-color: #fce4d6 !important; font-weight: bold !important; }
            .row-wait_buy { background-color: #fef9e7 !important; }
            .row-wait_sell { background-color: #f5eef8 !important; }
        </style>
        """
        
        table_data = []
        for item in reversed(log_list):
            rtn_color = "color: #27ae60 !important;" if item['rtn'] >= 0 else "color: #c0392b !important;"
            target_band_str = f"과열선: {item['upper']:.2f}" if "매도" in item['type'] else f"침체선: {item['lower']:.2f}"
            
            # 클래스명을 통해 간접적으로 CSS 스타일 매칭
            table_data.append(f"""
                <tr class="row-{item['style']}">
                    <td class="text-center">{item['date']}</td>
                    <td class="text-left">{item['type']}</td>
                    <td class="text-center font-bold" style="color: #1c3d5a !important;">{item['nsi']:.3f}</td>
                    <td class="text-center" style="color: #4b5563 !important;">{target_band_str}</td>
                    <td class="text-right">${item['price']:.2f}</td>
                    <td class="text-right font-bold" style="{rtn_color}">{item['rtn_label']}: {item['rtn']:+.2f}%</td>
                </tr>
            """)
            
        html_table = f"""
        {css_style}
        <div style="overflow-x: auto;">
            <table class="nsi-table">
                <thead>
                    <tr>
                        <th>📅 발생 일자</th>
                        <th>🚦 신호 구분</th>
                        <th>📊 당시 NSI</th>
                        <th>🎯 기준선</th>
                        <th>💵 당시 주가</th>
                        <th>📈 현재 성적</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(table_data)}
                </tbody>
            </table>
        </div>
        """
        st.markdown(html_table, unsafe_allow_html=True)

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
