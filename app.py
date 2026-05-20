import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 웹페이지 기본 브라우저 설정
st.set_page_config(page_title="NSI 그물망 매매 대시보드", layout="wide")
st.title("📊 NSI (Net Spread Index) 미국 주식 모니터링 시스템")

# 2. 사이드바 제어 영역
st.sidebar.header("⚙️ 설정 파라미터")
ticker = st.sidebar.text_input("미국 주식 티커 입력", value="TSLA").upper()
period = st.sidebar.selectbox("데이터 조회 기간", ["1y", "2y", "5y"], index=0)
nsi_window = st.sidebar.slider("NSI 평균 기준일수 (과열 판단용)", 10, 60, 20)
bb_std = st.sidebar.slider("볼린저 밴드 표준편차 배수", 1.0, 3.0, 1.5, step=0.1)

# 3. 데이터 수집 및 NSI 연산 로직
@st.cache_data(ttl=3600)
def load_and_calc_nsi(ticker, period, nsi_window, bb_std):
    # 야후 파이낸스 실시간 데이터 로드
    df = yf.download(ticker, period=period)
    if df.empty:
        return pd.DataFrame()
    
    # 🚨 [핵심 버그 수정] 최신 yfinance의 Multi-Index 칼럼 구조를 강제로 평탄화 (ValueError 완전 해결)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0) # 'MU', 'TSLA' 같은 하위 티커 레벨을 삭제하고 'Close', 'Open'만 남김
    
    df = df.squeeze() # 1차원 데이터 압축 안전장치
    
    # 그물망 이동평균선 생성 (5일선부터 60일선까지 5일 간격)
    ma_days = list(range(5, 65, 5))
    ma_cols = []
    for day in ma_days:
        col_name = f'MA_{day}'
        df[col_name] = df['Close'].rolling(window=day).mean()
        ma_cols.append(col_name)
    
    # NSI(그물망 확산 지수) 연산
    ma_std = df[ma_cols].std(axis=1) # 이평선들의 표준편차 (변동폭)
    raw_nsi = (ma_std / df['MA_20']) * 100 # 20일선 기준 비율 표준화
    
    # 방향성(+/-) 엔진 반영: 종가가 20일선 위면 +, 아래면 -
    direction = np.where(df['Close'] >= df['MA_20'], 1, -1)
    df['NSI'] = raw_nsi * direction
    
    # 통계적 임계치 조절을 위한 NSI 볼린저 밴드 연산
    df['NSI_MA'] = df['NSI'].rolling(window=nsi_window).mean()
    df['NSI_STD'] = df['NSI'].rolling(window=nsi_window).std()
    
    df['NSI_Upper'] = df['NSI_MA'] + (bb_std * df['NSI_STD'])
    df['NSI_Lower'] = df['NSI_MA'] - (bb_std * df['NSI_STD'])
    
    return df.dropna()

# 계산 수행
df = load_and_calc_nsi(ticker, period, nsi_window, bb_std)

if df.empty:
    st.error("티커가 유효하지 않거나 주가 데이터를 불러올 수 없습니다. 스펠링을 확인해 주세요.")
else:
    # 4. 오늘의 신호 정밀 판정 (T, T-1, T-2 일자 비교를 통한 2-Day Confirmation)
    today = df.iloc[-1]        # 오늘 (T)
    yesterday = df.iloc[-2]    # 어제 (T-1)
    two_days_ago = df.iloc[-3] # 그저께 (T-2)
    
    current_price = float(today['Close'])
    current_nsi = float(today['NSI'])
    upper_bound = float(today['NSI_Upper'])
    lower_bound = float(today['NSI_Lower'])
    
    signal = "⏳ 관망 (추세 유지 중)"
    color = "gray"
    comment = ""
    
    # 매수/매도 2일 연속 확인 필터 조건 정의
    was_buy_day1 = (float(yesterday['NSI']) < float(yesterday['NSI_Lower'])) and \
                    (float(yesterday['NSI']) > float(two_days_ago['NSI']))
    is_buy_day2 = current_nsi > float(yesterday['NSI'])
    
    was_sell_day1 = (float(yesterday['NSI']) > float(yesterday['NSI_Upper'])) and \
                     (float(yesterday['NSI']) < float(two_days_ago['NSI']))
    is_sell_day2 = current_nsi < float(yesterday['NSI'])
    
    # 최종 조건 분기 및 정량적 코멘트 매칭
    if was_buy_day1 and is_buy_day2:
        signal = "🔥 매수 타이밍 (2일 연속 반등 컨펌!)"
        color = "green"
        comment = """
        **🔍 현재 상황:** 역배열로 넓게 찢어지던 그물망이 이틀 연속 좁혀졌습니다. 시장의 과도한 공포와 투매가 진정되고, 바닥권에서 신뢰도 높은 저가 매수세가 유입되며 추세가 진짜로 돌아서기 시작했다는 강력한 증거입니다.
        
        **💡 대응 매뉴얼:** * 1일 차에 담아두었던 관심종목을 켜고 **본격적인 진입(매수)을 검토**할 최적의 타이밍입니다.
        * 안전한 자금 관리를 위해 20일 이평선까지의 이격 공간을 1차 목표가로 잡고 분할 매수로 접근하세요.
        """
    elif was_sell_day1 and is_sell_day2:
        signal = "🚨 매도 타이밍 (2일 연속 꺾임 컨펌!)"
        color = "red"
        comment = """
        **🔍 현재 상황:** 정배열 그물망이 극도로 벌어지며 하늘을 찌르던 상승 에너지가 이틀 연속으로 둔화되었습니다. 단기 차익 실현 물량이 대거 쏟아지고 있으며, 주가가 20일선(평균)으로 회귀하려는 강한 통계적 인력이 작용하고 있습니다.
        
        **💡 대응 매뉴얼:** * 탐욕에 눈멀어 무작정 버티기보다는 **안전하게 수익을 확실히 챙겨야(청산) 하는 구간**입니다.
        * 전량 매도가 아쉽다면 최소한 50% 이상 분할 매도하여 현금을 확보하고 다음 싸이클을 준비하세요.
        """
    elif (current_nsi < lower_bound) and (current_nsi > float(yesterday['NSI'])):
        signal = "👀 매수 대기 (반등 1일 차 - 내일까지 관찰)"
        color = "orange"
        comment = """
        **🔍 현재 상황:** 밑으로 쫙 펼쳐져 있던 하락 그물망이 오늘 처음으로 살짝 좁혀졌습니다. 낙폭과대에 따른 일시적인 기술적 반등(데드캣 바운스)일 가능성이 여전히 남아 있습니다.
        
        **💡 대응 매뉴얼:** * **섣부른 물타기나 즉각적인 매수는 금물**입니다. 관심종목에 등록하고 조용히 대기하세요.
        * 내일 종가 기준으로도 NSI 지수가 연속으로 상승하여 2일 차 컨펌이 나는지 확인하는 것이 안전합니다.
        """
    elif (current_nsi > upper_bound) and (current_nsi < float(yesterday['NSI'])):
        signal = "⚠️ 매도 대기 (고점 1일 차 - 내일까지 관찰)"
        color = "magenta"
        comment = """
        **🔍 현재 상황:** 그물망이 역대급으로 벌어지며 과매수 영역의 정점을 찍고 오늘 처음으로 꺾였습니다. 단기 상승 피로감이 한계에 달한 상태입니다.
        
        **💡 대응 매뉴얼:** * 신규 진입은 매우 위험한 자리이며, 기존 보유자라면 **슬슬 매도 주문을 준비해야 합니다.**
        * 다만 마지막 광기의 불꽃(오버슈팅)일 수 있으니 확실하게 내일 한 번 더 연속으로 꺾이는지 확인 후 대응해도 늦지 않습니다.
        """
    else:
        if current_nsi >= 0:
            comment = "**🔍 현재 상황:** 주가가 20일선 위에서 그물망의 탄탄한 지지를 받으며 안정적인 상승 흐름을 유지하고 있습니다. 과열권까지는 아직 여유가 있는 건강한 추세입니다. \n\n**💡 대응 매뉴얼:** 매도할 이유가 전혀 없습니다. 추세를 느긋하게 즐기며 기존 물량을 **보유(Hold)**하세요."
        else:
            comment = "**🔍 현재 상황:** 주가가 20일선 아래에서 역배열 그물망에 무겁게 짓눌려 하락 터널을 지나고 있습니다. \n\n**💡 대응 매뉴얼:** 바닥이 어디인지 알 수 없는 구간입니다. 물타기나 저점 예측 매수는 절대 금지하며 현금을 쥔 채 철저히 **관망**을 유지해야 합니다."

    # 5. 대시보드 스코어카드 및 코멘트 UI 렌더링
    col1, col2, col3 = st.columns(3)
    col1.metric(label=f"{ticker} 현재 종가", value=f"${current_price:.2f}")
    col2.metric(label="오늘의 NSI 지수", value=f"{current_nsi:.3f}")
    with col3:
        st.markdown(f"### 현재 신호: <span style='color:{color}'>{signal}</span>", unsafe_allow_html=True)
        
    st.info(comment)
    st.markdown("---")
    
    # ----------------------------------------------------
    # [과거 20일 신호 복기 및 수익률 백트래킹 로그]
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
        
        d_signal = None
        d_style = "normal" 
        
        w_buy1 = (float(y_day['NSI']) < float(y_day['NSI_Lower'])) and (float(y_day['NSI']) > float(t_2_day['NSI']))
        i_buy2 = d_nsi > float(y_day['NSI'])
        
        w_sell1 = (float(y_day['NSI']) > float(y_day['NSI_Upper'])) and (float(y_day['NSI']) < float(t_2_day['NSI']))
        i_sell2 = d_nsi < float(y_day['NSI'])
        
        if w_buy1 and i_buy2:
            d_signal = "🟩 [매수] 2일 차 최종 컨펌"
            d_style = "bold_buy"
        elif w_sell1 and i_sell2:
            d_signal = "🟥 [매도] 2일 차 최종 컨펌"
            d_style = "bold_sell"
        elif (d_nsi < d_lower) and (d_nsi > float(y_day['NSI'])):
            d_signal = "🟧 [매수 대기] 반등 1일 차"
        elif (d_nsi > d_upper) and (d_nsi < float(y_day['NSI'])):
            d_signal = "🟪 [매도 대기] 고점 1일 차"
            
        if d_signal:
            past_price = float(t_day['Close'])
            rtn = ((current_price - past_price) / past_price) * 100
            
            if "매도" in d_signal:
                rtn = ((past_price - current_price) / past_price) * 100
                rtn_str = f"하락 방어(익절 효과): **{rtn:+.2f}%**"
            else:
                rtn_str = f"현재 가상 수익률: **{rtn:+.2f}%**"
                
            date_str = t_day.name.strftime('%Y-%m-%d')
            log_list.append({'date': date_str, 'signal': d_signal, 'price': past_price, 'rtn_str': rtn_str, 'style': d_style})

    if not log_list:
        st.write("📆 최근 20일 동안 발생한 특이 매수/매도 신호가 없습니다. 평온한 추세 구간입니다.")
    else:
        for item in reversed(log_list):
            if item['style'] == "bold_buy":
                st.markdown(f"**📢 {item['date']}** | <span style='color:green; font-size:18px;'>**{item['signal']}**</span> | 발생 당시 주가: ${item['price']:.2f} $\rightarrow$ {item['rtn_str']}", unsafe_allow_html=True)
            elif item['style'] == "bold_sell":
                st.markdown(f"**📢 {item['date']}** | <span style='color:red; font-size:18px;'>**{item['signal']}**</span> | 발생 당시 주가: ${item['price']:.2f} $\rightarrow$ {item['rtn_str']}", unsafe_allow_html=True)
            else:
                st.markdown(f"⏳ {item['date']} | {item['signal']} | 발생 당시 주가: ${item['price']:.2f} | {item['rtn_str']}")

    st.markdown("---")
    
    # 6. Plotly 고해상도 인터랙티브 통합 차트 구현
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.08, row_heights=[0.6, 0.4])
    
    fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='Close', line=dict(color='black', width=2.5)), row=1, col=1)
    for col in [c for c in df.columns if 'MA_' in c]:
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
