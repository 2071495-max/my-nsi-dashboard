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
    
    # 🚨 최신 yfinance의 Multi-Index 2차원 데이터 구조를 1차원으로 압축 (ValueError 해결)
    df = df.squeeze()
    
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
    is_buy_day2 = current_nsi
