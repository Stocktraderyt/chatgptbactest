import pandas_market_calendars as mcal
import math
import pandas as pd
from datetime import timedelta 
import time
from datetime import datetime, timedelta
import plotly.graph_objects as go
import streamlit as st
from tvDatafeed import TvDatafeed, Interval 

st.set_page_config( 
    page_title="Demand And Supply daily zone scan engine For Indian Stock Market",  # Meta title
    page_icon="📈",  # Page icon (can be a string, or a path to an image)
    layout="wide",  # Layout configuration
)
# Hide Streamlit style elements
hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# Add a meta description
st.markdown(
    """
    <meta name="description" content="This is a Demand And Supply daily zone scan engine For Indian Stock Market.If you know about drop base rally and rally base rally or rally base drop and drop base drop pattern then this scanner can be useful for you">
    """,
    unsafe_allow_html=True
)

def calculate_atr(stock_data, length=14):
    stock_data['previous_close'] = stock_data['Close'].shift(1)
    stock_data['tr1'] = abs(stock_data['High'] - stock_data['Low'])
    stock_data['tr2'] = abs(stock_data['High'] - stock_data['previous_close'])
    stock_data['tr3'] = abs(stock_data['Low'] - stock_data['previous_close'])
    stock_data['TR'] = stock_data[['tr1', 'tr2', 'tr3']].max(axis=1)

    def rma(series, length):
        alpha = 1 / length
        return series.ewm(alpha=alpha, adjust=False).mean()

    stock_data['ATR'] = rma(stock_data['TR'], length)
    stock_data['Candle_Range'] = stock_data['High'] - stock_data['Low']
    stock_data['Candle_Body'] = abs(stock_data['Close'] - stock_data['Open'])
    return stock_data

def capture_ohlc_data(stock_data, exit_index, i):
    start_index = max(0, i - 12)
    end_index = min(len(stock_data), exit_index+12 if exit_index is not None else (i + 12))
    ohlc_data = stock_data.iloc[start_index:end_index]
    return ohlc_data
    
def check_golden_crossover(stock_data_htf, pulse_check_start_date):
    result = ""  # Initialize an empty string to store the result
    trend_label = ""  # Initialize trend_label
    try:
        # Calculate EMA20 and EMA50
        stock_data_htf['EMA20'] = stock_data_htf['Close'].ewm(span=20, adjust=False).mean().round(2)
        stock_data_htf['EMA50'] = stock_data_htf['Close'].ewm(span=50, adjust=False).mean().round(2)

        # Drop rows with NaN values in EMA columns
        stock_data_htf.dropna(subset=['EMA20', 'EMA50'], inplace=True)

        # Identify crossover points
        crossover_up = stock_data_htf['EMA20'] > stock_data_htf['EMA50']
        crossover_down = stock_data_htf['EMA20'] < stock_data_htf['EMA50']

        # Localize pulse_check_start_date to 'Asia/Kolkata'
        pulse_check_start_date = pulse_check_start_date.tz_localize('Asia/Kolkata')

        # Find the last index before the target date
        last_index_before_staring_check = stock_data_htf.index[stock_data_htf.index < pulse_check_start_date]

        if not last_index_before_staring_check.empty:
            last_index_before_staring_check = last_index_before_staring_check[-1]

            # Check crossover conditions just before the target date
            if crossover_up.loc[last_index_before_staring_check]:
                # Check if the crossover candle is bullish or bearish
                if stock_data_htf['Close'].loc[last_index_before_staring_check] > stock_data_htf['Open'].loc[last_index_before_staring_check]:
                    result = "Pulse✅ Candle✅"
                else:
                    result = "Pulse✅ Candle❌"
            elif crossover_down.loc[last_index_before_staring_check]:
                # Check if the crossover candle is bullish or bearish
                if stock_data_htf['Close'].loc[last_index_before_staring_check] > stock_data_htf['Open'].loc[last_index_before_staring_check]:
                    result = "Pulse❌ Candle✅"
                else:
                    result = "Pulse❌ Candle❌ "
            else:
                result = "invalid pulse"

            # New logic for trend label
            latest_candle_close = stock_data_htf['Close'].iloc[-1]
            latest_candle_low = stock_data_htf['Low'].iloc[-1]
            latest_candle_high = stock_data_htf['High'].iloc[-1]
            latest_closing_price = round(stock_data_htf['Close'].iloc[-1], 2)
            ema20 = stock_data_htf['EMA20']

            if (latest_candle_close == ema20.iloc[-1] or 
                (latest_candle_low <= ema20.iloc[-1] and latest_candle_high >= ema20.iloc[-1])):
                trend_label = "➡️ sideways"
            elif (latest_candle_close > ema20.iloc[-8] and latest_candle_close > ema20.iloc[-1]):
                trend_label = "✅ Up"
            elif (latest_candle_close < ema20.iloc[-8] and latest_candle_close < ema20.iloc[-1]):
                trend_label = "❌ Down"

        else:
            result = "No data"

    except Exception as e:
        result = f"NA"

    return result, trend_label  # Return the result string and trend label

def find_patterns(ticker, stock_data,stock_data_htf, interval, max_base_candles, 
                  scan_demand_zone_allowed, scan_supply_zone_allowed,reward_value,fresh_zone_allowed,target_zone_allowed,stoploss_zone_allowed,htf_interval,user_input_zone_distance):
    try:
        patterns = []
        last_legout_high = []  # Initialize here to avoid error
        last_legout_low = [ ] # Intiialize here to avoid error
        
        if len(stock_data) < 3:
            print(f"Not enough stock_data for {ticker}")
            return []

        for i in range(len(stock_data) - 1, 2, -1):
            if scan_demand_zone_allowed and (stock_data['Close'].iloc[i] > stock_data['Open'].iloc[i] and 
                stock_data['TR'].iloc[i] > stock_data['ATR'].iloc[i] and 
                stock_data['Open'].iloc[i] >= stock_data['Close'].iloc[i - 1]): # Opening of first legout should greater than 0.15% of boring closing                 
                
                first_legout_candle_body = abs(stock_data['Close'].iloc[i] - stock_data['Open'].iloc[i])
                first_legout_candle_range = (stock_data['High'].iloc[i] - stock_data['Low'].iloc[i])

                if first_legout_candle_body >= 0.5 * first_legout_candle_range:
                    high_prices = []
                    low_prices = []
                    for base_candles_count in range(1, max_base_candles + 1):
                        base_candles_found = 0
                        
                        legin_candle_index = i - (base_candles_count + 1)
                        legin_candle_body = stock_data['Candle_Body'].iloc[legin_candle_index]
                        legin_candle_range = stock_data['Candle_Range'].iloc[legin_candle_index]
                        
                        for k in range(1, base_candles_count + 1):
                            if (stock_data['ATR'].iloc[i - k] > stock_data['TR'].iloc[i - k] and 
                                legin_candle_body >= 0.50 * legin_candle_range):
                                
                                base_candles_found += 1
                                high_prices.append(stock_data['High'].iloc[i - k])
                                low_prices.append(stock_data['Low'].iloc[i - k])
                                
                            max_high_price = max(high_prices) if high_prices else None
                            min_low_price = min(low_prices) if low_prices else None
                            
                            if  max_high_price is not None and min_low_price is not None:
                                actual_base_candle_range = max_high_price - min_low_price
                            actual_legout_candle_range = None
                            first_legout_candle_range_for_one_two_ka_four = (stock_data['High'].iloc[i] - stock_data['Close'].iloc[i-1])    
                            condition_met = False  # Flag to check if any condition was met
    
                            
                            if base_candles_found == base_candles_count:
                                if ( 
                                    legin_candle_range >= 2 * actual_base_candle_range and
                                    first_legout_candle_range_for_one_two_ka_four >= 2 * legin_candle_range and 
                                    
                                    stock_data['Low'].iloc[i] >= stock_data['Low'].iloc[legin_candle_index]):
                                    condition_met = True  # Set flag if this condition is met
                                    # Add your logic here if needed

                                else:  # This is the else part for the if statement above
                                    last_legout_high = []
                                    j = i + 1
                                    while j in range(i + 1, min(i + 3, len(stock_data))) and stock_data['Close'].iloc[j] > stock_data['Open'].iloc[j]:
                                        # Check if j == i + 1
                                        if j == i + 1:
                                            if (stock_data['Open'].iloc[j] >= 0.10* stock_data['Close'].iloc[i] and 
                                                stock_data['Low'].iloc[j] >= 0.50 * stock_data['Candle_Range'].iloc[i]):
                                                last_legout_high.append(stock_data['High'].iloc[j])
        
                                        # Check if j == i + 2
                                        elif j == i + 2:
                                            if stock_data['Low'].iloc[j] >= stock_data['Low'].iloc[i + 1]:
                                                last_legout_high.append(stock_data['High'].iloc[j])
        
                                        j += 1

                                    last_legout_high_value = max(last_legout_high) if last_legout_high else None

                                    if last_legout_high_value is not None:
                                        actual_legout_candle_range = last_legout_high_value - stock_data['Close'].iloc[i - 1]

                                        if (legin_candle_range >= 2 * actual_base_candle_range and 
                                            actual_legout_candle_range >= 2 * legin_candle_range and
                                            stock_data['Low'].iloc[i] >= stock_data['Low'].iloc[legin_candle_index]):
                
                                            condition_met = True  # Set flag if this condition is met

                            
                            # Code block to execute if any condition was met
                            if condition_met:
                                if interval in ('1 Day','1 Week','1 Month'):
                                    legin_date = stock_data.index[legin_candle_index].strftime('%Y-%m-%d')
                                    legout_date = stock_data.index[i].strftime('%Y-%m-%d')
                                else:
                                    legin_date = stock_data.index[legin_candle_index].strftime('%Y-%m-%d %H:%M:%S')
                                    legout_date = stock_data.index[i].strftime('%Y-%m-%d %H:%M:%S')
                                
                                if actual_legout_candle_range is not None:
                                    legout_candle_range = actual_legout_candle_range
                                else:
                                    legout_candle_range = first_legout_candle_range_for_one_two_ka_four


                                entry_occurred = False
                                target_hit = False
                                stop_loss_hit = False
                                entry_date = None
                                entry_index = None
                                exit_date = None
                                exit_index = None
                                Zone_status = None
                                total_risk = max_high_price - min_low_price
                                minimum_target = (total_risk * reward_value) + max_high_price                  
                                start_index = j+1 if last_legout_high else i + 1

                                for m in range(start_index, len(stock_data)):
                                    if not entry_occurred:
                                        # Check if the entry condition is met
                                        if stock_data['Low'].iloc[m] <= max_high_price:
                                            entry_occurred = True
                                            entry_index = m
                                            entry_date = stock_data.index[m].strftime('%Y-%m-%d %H:%M:%S')

                                            # Check if the low and high of the current candle exceed the limits
                                            if stock_data['Low'].iloc[m] < min_low_price:
                                                stop_loss_hit = True
                                                exit_index = m
                                                exit_date = stock_data.index[m].strftime('%Y-%m-%d %H:%M:%S')
                                                Zone_status = 'Stop loss'
                                                break  # Exit the loop after stop-loss is hit
                                            elif stock_data['High'].iloc[m] >= minimum_target:
                                                target_hit = True
                                                exit_index = m
                                                exit_date = stock_data.index[m].strftime('%Y-%m-%d %H:%M:%S')
                                                Zone_status = 'Target'
                                                break  # Exit the loop after target is hit
                                        elif min(stock_data['Low'].iloc[start_index:]) > max_high_price:
                                             Zone_status = 'Fresh'
                                    else:
                                        # After entry, check if price hits stop-loss or minimum target
                                        if stock_data['Low'].iloc[m] < min_low_price:
                                            stop_loss_hit = True
                                            exit_index = m
                                            exit_date = stock_data.index[m].strftime('%Y-%m-%d %H:%M:%S')
                                            Zone_status = 'Stop loss'
                                            break  # Exit the loop after stop-loss is hit
                                        elif stock_data['High'].iloc[m] >= minimum_target:
                                            target_hit = True
                                            exit_index = m
                                            exit_date = stock_data.index[m].strftime('%Y-%m-%d %H:%M:%S')
                                            Zone_status = 'Target'
                                            break  # Exit the loop after target is hit
                                
                                # time_in_exit = exit_index - entry_index                                
                                Pattern_name_is = 'DZ(DBR)' if stock_data['Open'].iloc[legin_candle_index] > stock_data['Close'].iloc[legin_candle_index] else 'DZ(RBR)'
                                latest_closing_price = round(stock_data['Close'].iloc[-1], 2)
                                zone_distance = (math.floor(latest_closing_price) - max(high_prices)) / max(high_prices) * 100
                                legin_base_legout_ranges = f"{round(legin_candle_range)}:{round(actual_base_candle_range)}:{round(legout_candle_range)}"
                                
                                ohlc_data = capture_ohlc_data(stock_data, exit_index, i)
                                
                                pulse_check_start_date = pd.Timestamp(entry_date) if entry_date is not None else pd.Timestamp.now()

                                pulse_details,trend_label = check_golden_crossover(stock_data_htf, pulse_check_start_date)       
                                
                                if ((fresh_zone_allowed and Zone_status == 'Fresh') or \
                                   (target_zone_allowed and Zone_status == 'Target') or \
                                   (stoploss_zone_allowed and Zone_status == 'Stop loss')) and zone_distance <= user_input_zone_distance:
                                    patterns.append({
                                        'Symbol': ticker, 
                                        'Time frame': interval,
                                        'Pulse_details': pulse_details, 
                                        'Trend':trend_label,
                                        'Zone_status':Zone_status,
                                        'Zone_Type' : Pattern_name_is,
                                        'Entry_Price':max_high_price,
                                        'Stop_loss': min_low_price,
                                        'Target': minimum_target,
                                        'Entry_date':entry_date,
                                        'Exit_date':exit_date,
                                        'Exit_index' :exit_index ,  
                                        'Entry_index' :entry_index ,  
                                        'Zone_Distance': zone_distance.round(2),
                                        'legin_date': legin_date,
                                        'base_count': base_candles_found,
                                        'legout_date': legout_date,
                                        'legin:base:legout_ranges': legin_base_legout_ranges,
                                        'OHLC_Data': ohlc_data,
                                        'Close_price': latest_closing_price
                                    })

            if scan_supply_zone_allowed and (stock_data['Open'].iloc[i] > stock_data['Close'].iloc[i] and 
                stock_data['TR'].iloc[i] > stock_data['ATR'].iloc[i] and 
                stock_data['Open'].iloc[i] <=  stock_data['Close'].iloc[i - 1]): 
                    
                first_legout_candle_body = abs(stock_data['Close'].iloc[i] - stock_data['Open'].iloc[i])
                first_legout_candle_range = (stock_data['High'].iloc[i] - stock_data['Low'].iloc[i])

                if first_legout_candle_body >= 0.5 * first_legout_candle_range:
                    high_prices = []
                    low_prices = []
                    for base_candles_count in range(1, max_base_candles + 1):
                        base_candles_found = 0
                        
                        legin_candle_index = i - (base_candles_count + 1)
                        legin_candle_body = stock_data['Candle_Body'].iloc[legin_candle_index]
                        legin_candle_range = stock_data['Candle_Range'].iloc[legin_candle_index]
                        
                        for k in range(1, base_candles_count + 1):
                            if (stock_data['ATR'].iloc[i - k] > stock_data['TR'].iloc[i - k] and 
                                legin_candle_body >= 0.50 * legin_candle_range):
                                
                                base_candles_found += 1
                                high_prices.append(stock_data['High'].iloc[i - k])
                                low_prices.append(stock_data['Low'].iloc[i - k])
                                
                            max_high_price = max(high_prices) if high_prices else None
                            min_low_price = min(low_prices) if low_prices else None
                            
                            if max_high_price is not None and min_low_price is not None:
                                actual_base_candle_range = max_high_price - min_low_price
                            actual_legout_candle_range = None
                            first_legout_candle_range_for_one_two_ka_four = (stock_data['Close'].iloc[i-1] - stock_data['Low'].iloc[i])    
                            condition_met = False  # Flag to check if any condition was met


   
                            if base_candles_found == base_candles_count:
                                if (legin_candle_range >= 2 * actual_base_candle_range and
                                    first_legout_candle_range_for_one_two_ka_four >= 2 * legin_candle_range and 
                                    
                                    stock_data['High'].iloc[i] <= stock_data['High'].iloc[legin_candle_index]):
                                    condition_met = True  # Set flag if this condition is met
                                    # Add your logic here if needed

                                else:  # This is the else part for the if statement above
                                    last_legout_low = []
                                    j = i + 1
                                    while j in range(i + 1, min(i + 3, len(stock_data))) and stock_data['Open'].iloc[j] > stock_data['Close'].iloc[j]:
                                        # Check if j == i + 1
                                        if j == i + 1:
                                            if (stock_data['Open'].iloc[j] <= 0.10* stock_data['Close'].iloc[i] and 
                                                stock_data['High'].iloc[j] <= 0.50 * stock_data['Candle_Range'].iloc[i]):
                                                last_legout_low.append(stock_data['Low'].iloc[j])
        
                                        # Check if j == i + 2
                                        elif j == i + 2:
                                            if stock_data['High'].iloc[j] <= stock_data['High'].iloc[i + 1]:
                                                last_legout_low.append(stock_data['Low'].iloc[j])
        
                                        j += 1

                                    last_legout_low_value = min(last_legout_low) if last_legout_low else None

                                    if last_legout_low_value is not None:
                                        actual_legout_candle_range = abs(last_legout_low_value - stock_data['Close'].iloc[i - 1])

                                        if (legin_candle_range >= 2 * actual_base_candle_range and 
                                            actual_legout_candle_range >= 2 * legin_candle_range and
                                            stock_data['High'].iloc[i] <= stock_data['High'].iloc[legin_candle_index]):
                
                                            condition_met = True  # Set flag if this condition is met
                            
                            # Code block to execute if any condition was met
                            if condition_met:
                                if interval in ('1 Day','1 Week','1 Month') :
                                    legin_date = stock_data.index[legin_candle_index].strftime('%Y-%m-%d')
                                    legout_date = stock_data.index[i].strftime('%Y-%m-%d')
                                else:
                                    legin_date = stock_data.index[legin_candle_index].strftime('%Y-%m-%d %H:%M:%S')
                                    legout_date = stock_data.index[i].strftime('%Y-%m-%d %H:%M:%S')
                                
                                if actual_legout_candle_range is not None:
                                    legout_candle_range = actual_legout_candle_range
                                else:
                                    legout_candle_range = first_legout_candle_range_for_one_two_ka_four


                                entry_occurred = False
                                target_hit = False
                                stop_loss_hit = False
                                entry_date = None
                                entry_index = None
                                exit_date = None
                                exit_index = None
                                Zone_status = None
                                total_risk = max_high_price - min_low_price
                                minimum_target = min_low_price - (total_risk * reward_value)                   
                                start_index = j+1 if last_legout_low else i + 1

                                for m in range(start_index, len(stock_data)):
                                    if not entry_occurred:
                                        # Check if the entry condition is met
                                        if stock_data['High'].iloc[m] >= min_low_price:
                                            entry_occurred = True
                                            entry_index = m
                                            entry_date = stock_data.index[m].strftime('%Y-%m-%d %H:%M:%S')

                                            # Check if the low and high of the current candle exceed the limits
                                            if stock_data['High'].iloc[m] > max_high_price:
                                                stop_loss_hit = True
                                                exit_index = m
                                                exit_date = stock_data.index[m].strftime('%Y-%m-%d %H:%M:%S')
                                                Zone_status = 'Stop loss'
                                                break  # Exit the loop after stop-loss is hit
                                            elif stock_data['Low'].iloc[m] <= minimum_target:
                                                target_hit = True
                                                exit_index = m
                                                exit_date = stock_data.index[m].strftime('%Y-%m-%d %H:%M:%S')
                                                Zone_status = 'Target'
                                                break  # Exit the loop after target is hit
                                        elif max(stock_data['High'].iloc[start_index:]) < min_low_price:
                                             Zone_status = 'Fresh'
                                    else:
                                        # After entry, check if price hits stop-loss or minimum target
                                        if stock_data['High'].iloc[m] > max_high_price:
                                            stop_loss_hit = True
                                            exit_index = m
                                            exit_date = stock_data.index[m].strftime('%Y-%m-%d %H:%M:%S')
                                            Zone_status = 'Stop loss'
                                            break  # Exit the loop after stop-loss is hit
                                        elif stock_data['Low'].iloc[m] <= minimum_target:
                                            target_hit = True
                                            exit_index = m
                                            exit_date = stock_data.index[m].strftime('%Y-%m-%d %H:%M:%S')
                                            Zone_status = 'Target'
                                            break  # Exit the loop after target is hit

                                
                                Pattern_name_is = 'SZ(RBD)' if stock_data['Close'].iloc[legin_candle_index] > stock_data['Open'].iloc[legin_candle_index] else 'SZ(DBD)'
                                latest_closing_price = round(stock_data['Close'].iloc[-1], 2)
                                zone_distance = (min(low_prices) - math.floor(latest_closing_price)) / min(low_prices) * 100
                                legin_base_legout_ranges = f"{round(legin_candle_range, 2)}:{round(actual_base_candle_range, 2)}:{round(legout_candle_range, 2)}"
                                
                                ohlc_data = capture_ohlc_data(stock_data, exit_index, i)
                                
                                pulse_check_start_date = pd.Timestamp(entry_date) if entry_date is not None else pd.Timestamp.now()
                                pulse_details,trend_label = check_golden_crossover(stock_data_htf, pulse_check_start_date)
                                
                                if ((fresh_zone_allowed and Zone_status == 'Fresh') or \
                                   (target_zone_allowed and Zone_status == 'Target') or \
                                   (stoploss_zone_allowed and Zone_status == 'Stop loss')) and zone_distance <= user_input_zone_distance:
                                   patterns.append({
                                        'Symbol': ticker, 
                                        'Time frame':interval,                                       
                                        'Pulse_details': pulse_details, 
                                        'Trend':trend_label,                                       
                                        'Zone_status':Zone_status,
                                        'Zone_Type' : Pattern_name_is,
                                        'Entry_Price':max_high_price,
                                        'Stop_loss': min_low_price,
                                        'Target': minimum_target,
                                        'Entry_date':entry_date,
                                        'Exit_date':exit_date,
                                        'Exit_index' :exit_index ,  
                                        'Entry_index' :entry_index ,                                                                            
                                        'Zone_Distance': zone_distance.round(2),
                                        'legin_date': legin_date,
                                        'base_count': base_candles_found,
                                        'legout_date': legout_date,
                                        'legin:base:legout_ranges': legin_base_legout_ranges,
                                        'OHLC_Data': ohlc_data,
                                        'Close_price': latest_closing_price
                                    })
                              
        return patterns
    except Exception as e:
        print(f"Error processing {ticker}: {e}")
        return []

# Initialize TvDatafeed with your TradingView credentials
tv = TvDatafeed('AKTradingWithSL', 'Bulky@001122')

st.markdown(f"<h3 style=\"text-align: center;\"> 😊 Welcome to demand - supply daily zone scan engine </h1>", unsafe_allow_html=True)

with st.form(key='my_form'):
    ticker_option = st.radio("Step-1: Select script type", ["Custom Symbol", "FnO Stocks","Intraday Stocks", "Nifty50stocks", "Nifty100stocks", "Nifty200stocks", "Nifty500stocks"], horizontal=True)

    if ticker_option == "Custom Symbol":
       user_tickers = st.text_input("Enter valid symbols (comma-separated):","SBIN, TCS, ITC")
       tickers = [ticker.strip() for ticker in user_tickers.split(',')]
    elif ticker_option == "FnO Stocks":
       tickers = ['COFORGE', 'FEDERALBNK', 'OBEROIRLTY', 'CUMMINSIND', 'EICHERMOT', 'M&M', 'RAMCOCEM', 'ULTRACEMCO', 'ABFRL', 'GODREJPROP', 'PAGEIND', 'PETRONET', 'BSOFT', 'ACC', 'LT', 'GRASIM', 'SHREECEM', 'ABB', 'CANFINHOME', 'TRENT', 'HDFCLIFE', 'GUJGASLTD', 'LTTS', 'SBIN', 'MRF', 'ASHOKLEY', 'SIEMENS', 'MARUTI', 'CONCOR', 'MOTHERSON', 'TATACOMM', 'NTPC', 'ITC', 'APOLLOHOSP', 'DALBHARAT', 'BAJFINANCE', 'MGL', 'BAJAJFINSV', 'ADANIPORTS', 'MPHASIS', 'GODREJCP', 'NMDC', 'ADANIENT', 'ICICIGI', 'LALPATHLAB', 'TORNTPHARM', 'LUPIN', 'PFC', 'HINDUNILVR', 'IRCTC', 'ICICIBANK', 'PNB', 'IPCALAB', 'SBILIFE', 'KOTAKBANK', 'DABUR', 'INDIAMART', 'CHOLAFIN', 'LTIM', 'SUNTV', 'GAIL', 'NESTLEIND', 'BHARATFORG', 'BANKBARODA', 'CANBK', 'TATAPOWER', 'DRREDDY', 'HEROMOTOCO', 'LAURUSLABS', 'M&MFIN', 'HAL', 'INDIGO', 'UPL', 'INDUSINDBK', 'TITAN', 'UBL', 'GNFC', 'MFSL', 'SUNPHARMA', 'BOSCHLTD', 'AXISBANK', 'JUBLFOOD', 'JINDALSTEL', 'AUROPHARMA', 'TATACONSUM', 'PIDILITIND', 'VOLTAS', 'SYNGENE', 'AMBUJACEM', 'RECLTD', 'ASTRAL', 'ASIANPAINT', 'BATAINDIA', 'DLF', 'TATAMOTORS', 'INDHOTEL', 'IGL', 'BEL', 'NAVINFLUOR', 'RELIANCE', 'CIPLA', 'ESCORTS', 'INFY', 'BHARTIARTL', 'BAJAJ-AUTO', 'TATASTEEL', 'METROPOLIS', 'ALKEM', 'BRITANNIA', 'COLPAL', 'PVRINOX', 'ICICIPRULI', 'MUTHOOTFIN', 'EXIDEIND', 'TCS', 'LICHSGFIN', 'Time frame', 'IOC', 'OFSS', 'TVSMOTOR', 'INDUSTOWER', 'BALKRISIND', 'TECHM', 'COALINDIA', 'BALRAMCHIN', 'BIOCON', 'NAUKRI', 'SBICARD', 'BERGEPAINT', 'INDIACEM', 'JSWSTEEL', 'IDFCFIRSTB', 'HDFCBANK', 'HAVELLS', 'ABCAPITAL', 'HDFCAMC', 'DEEPAKNTR', 'PEL', 'BPCL', 'RBLBANK', 'ZYDUSLIFE', 'AUBANK', 'MANAPPURAM', 'PIIND', 'SAIL', 'POWERGRID', 'WIPRO', 'DIVISLAB', 'COROMANDEL', 'HCLTECH', 'ATUL', 'POLYCAB', 'SRF', 'ABBOTINDIA', 'BHEL', 'AARTIIND', 'IEX', 'MCX', 'HINDALCO', 'HINDPETRO', 'BANDHANBNK', 'CUB', 'IDFC', 'TATACHEM', 'MARICO', 'IDEA', 'ONGC', 'GRANULES', 'DIXON', 'JKCEMENT', 'APOLLOTYRE', 'GMRINFRA', 'GLENMARK', 'CHAMBLFERT', 'PERSISTENT', 'CROMPTON', 'SHRIRAMFIN', 'HINDCOPPER', 'NATIONALUM', 'VEDL']
    elif ticker_option == "Intraday Stocks":
       tickers = ['TATASTEEL', 'MOTHERSON', 'NYKAA', 'NMDC', 'GAIL', 'BANKBARODA', 'ZOMATO', 'ASHOKLEY', 'BEL', 'JIOFIN', 'ONGC', 'POWERGRID', 'BPCL', 'PETRONET', 'NTPC', 'HINDPETRO', 'TATAPOWER', 'INDUSTOWER', 'VEDL', 'ITC', 'COALINDIA', 'PFC', 'KALYANKJIL', 'RECLTD', 'DABUR', 'MARICO', 'INDHOTEL', 'CGPOWER', 'HINDALCO', 'SBICARD', 'HDFCLIFE', 'OIL', 'JSL', 'SBIN', 'MAXHEALTH', 'JSWSTEEL', 'CONCOR', 'JINDALSTEL', 'TATAMOTORS', 'UNOMINDA', 'AXISBANK', 'TATACONSUM', 'ICICIBANK', 'INDUSINDBK', 'CHOLAFIN', 'UNITDSPR', 'GODREJCP', 'ADANIPORTS', 'VBL', 'AUROPHARMA', 'BHARATFORG', 'BHARTIARTL', 'TECHM', 'HDFCBANK', 'CIPLA', 'TORNTPOWER', 'VOLTAS', 'HCLTECH', 'COROMANDEL', 'POLICYBZR', 'OBEROIRLTY', 'KOTAKBANK', 'PRESTIGE', 'KPITTECH', 'SUNPHARMA', 'SBILIFE', 'HAVELLS', 'ASTRAL', 'INFY', 'TATACOMM', 'ICICIGI', 'LUPIN', 'SRF', 'GRASIM', 'HINDUNILVR', 'M&M', 'TVSMOTOR', 'BALKRISIND', 'GODREJPROP', 'RELIANCE', 'MPHASIS', 'ASIANPAINT', 'SHRIRAMFIN', 'TITAN', 'COLPAL', 'LT', 'CUMMINSIND', 'PHOENIXLTD']
    
    elif ticker_option == "Nifty50stocks":
        tickers = ['EICHERMOT', 'NTPC', 'ITC', 'GRASIM', 'APOLLOHOSP', 'LT', 'ULTRACEMCO', 'HINDUNILVR', 'TATACONSUM', 'SUNPHARMA', 'INFY', 'CIPLA', 'MARUTI', 'DRREDDY', 'ADANIPORTS', 'NESTLEIND', 'TCS', 'HEROMOTOCO', 'KOTAKBANK', 'ADANIENT', 'BAJAJ-AUTO', 'AXISBANK', 'M&M', 'SBIN', 'ICICIBANK', 'INDUSINDBK', 'TITAN', 'TATAMOTORS', 'LTIM', 'RELIANCE', 'BAJFINANCE', 'TECHM', 'BHARTIARTL', 'HDFCLIFE', 'WIPRO', 'ASIANPAINT', 'DIVISLAB', 'BAJAJFINSV', 'SBILIFE', 'COALINDIA', 'BRITANNIA', 'HCLTECH', 'HDFCBANK', 'TATASTEEL', 'POWERGRID', 'JSWSTEEL', 'ONGC', 'BPCL', 'HINDALCO', 'SHRIRAMFIN']
    elif ticker_option == "Nifty100stocks":
        tickers = ['ADANIGREEN', 'ADANIPOWER', 'EICHERMOT', 'NTPC', 'LICI', 'ATGL', 'ADANIENSOL', 'GRASIM', 'ULTRACEMCO', 'TORNTPHARM', 'ITC', 'DMART', 'SHREECEM', 'APOLLOHOSP', 'LT', 'HINDUNILVR', 'TATACONSUM', 'PIDILITIND', 'DRREDDY', 'MARUTI', 'SUNPHARMA', 'BANKBARODA', 'ADANIPORTS', 'INFY', 'PNB', 'SBIN', 'HEROMOTOCO', 'IRFC', 'ADANIENT', 'ABB', 'KOTAKBANK', 'CIPLA', 'INDUSINDBK', 'MOTHERSON', 'BAJAJ-AUTO', 'M&M', 'TITAN', 'ICICIBANK', 'GAIL', 'AXISBANK', 'IRCTC', 'LTIM', 'TRENT', 'TCS', 'COLPAL', 'NAUKRI', 'CANBK', 'NESTLEIND', 'AMBUJACEM', 'TATAMTRDVR', 'GODREJCP', 'TATAMOTORS', 'HDFCLIFE', 'BHARTIARTL', 'SRF', 'JIOFIN', 'ASIANPAINT', 'RELIANCE', 'ICICIGI', 'DABUR', 'TECHM', 'BERGEPAINT', 'BEL', 'BAJAJFINSV', 'BAJFINANCE', 'TVSMOTOR', 'RECLTD', 'BRITANNIA', 'INDIGO', 'PFC', 'BOSCHLTD', 'COALINDIA', 'WIPRO', 'IOC', 'TATASTEEL', 'DIVISLAB', 'SIEMENS', 'POWERGRID', 'SBILIFE', 'HCLTECH', 'ONGC', 'HAL', 'VBL', 'BAJAJHLDNG', 'JSWSTEEL', 'BPCL', 'TATAPOWER', 'MARICO', 'HDFCBANK', 'ZYDUSLIFE', 'CHOLAFIN', 'HINDALCO', 'SBICARD', 'HAVELLS', 'DLF', 'ICICIPRULI', 'ZOMATO', 'JINDALSTEL','SHRIRAMFIN', 'VEDL']        
    elif ticker_option == "Nifty200stocks":
        tickers = ['SUZLON', 'ADANIGREEN', 'ADANIPOWER', 'FEDERALBNK', 'OBEROIRLTY', 'COFORGE', 'OIL', 'EICHERMOT', 'JSWENERGY', 'MRF', 'BSE', 'PETRONET', 'TORNTPOWER', 'NTPC', 'LICI', 'ATGL', 'ADANIENSOL', 'DELHIVERY', 'JSWINFRA', 'GRASIM', 'TATATECH', 'TORNTPHARM', 'DMART', 'ULTRACEMCO', 'ITC', 'SHREECEM', 'ZEEL', 'DALBHARAT', 'APOLLOHOSP', 'LT', 'ACC', 'INDUSTOWER', 'PRESTIGE', 'TATACONSUM', 'NYKAA', 'PIDILITIND', 'HINDUNILVR', 'BDL', 'MARUTI', 'FORTIS', 'DRREDDY', 'GODREJPROP', 'PAGEIND', 'CONCOR', 'SUNPHARMA', 'ADANIPORTS', 'SBIN', 'GUJGASLTD', 'LTTS', 'GLAND', 'RVNL', 'ADANIENT', 'CIPLA', 'IRFC', 'INFY', 'LUPIN', 'UNIONBANK', 'BANKBARODA', 'PNB', 'KOTAKBANK', 'ASHOKLEY', 'HEROMOTOCO', 'LALPATHLAB', 'LODHA', 'ICICIBANK', 'MPHASIS', 'BAJAJ-AUTO', 'ABB', 'INDUSINDBK', 'MOTHERSON', 'CUMMINSIND', 'TITAN', 'AXISBANK', 'TCS', 'M&M', 'IRCTC', 'HDFCLIFE', 'GAIL', 'ALKEM', 'BHARATFORG', 'IPCALAB', 'TRENT', 'NAUKRI', 'UPL', 'AMBUJACEM', 'BAJAJFINSV', 'BHARTIARTL', 'IGL', 'ICICIGI', 'MAXHEALTH', 'TATAMTRDVR', 'CANBK', 'NESTLEIND', 'GODREJCP', 'AUROPHARMA', 'BALKRISIND', 'LTIM', 'MANKIND', 'TATAMOTORS', 'SUNTV', 'HDFCAMC', 'VOLTAS', 'CGPOWER', 'BAJFINANCE', 'OFSS', 'TATAELXSI', 'ASIANPAINT', 'COLPAL', 'RELIANCE', 'PFC', 'ESCORTS', 'JIOFIN', 'TATACOMM', 'TECHM', 'BERGEPAINT', 'BANKINDIA', 'HAL', 'INDIGO', 'SRF', 'DABUR', 'RECLTD', 'BEL', 'NMDC', 'SBILIFE', 'BRITANNIA', 'INDHOTEL', 'BOSCHLTD', 'COALINDIA', 'DIVISLAB', 'TVSMOTOR', 'LICHSGFIN', 'M&MFIN', 'POONAWALLA', 'WIPRO', 'SJVN', 'SIEMENS', 'APLAPOLLO', 'HCLTECH', 'VBL', 'AUBANK', 'SYNGENE', 'JSWSTEEL', 'PAYTM', 'ONGC', 'BAJAJHLDNG', 'IOC', 'HDFCBANK', 'MAZDOCK', 'NHPC', 'JUBLFOOD', 'POWERGRID', 'TATASTEEL', 'TIINDIA', 'ABFRL', 'CHOLAFIN', 'DEEPAKNTR', 'Time frame', 'LAURUSLABS', 'HINDPETRO', 'PIIND', 'TATAPOWER', 'BIOCON', 'MARICO', 'SAIL', 'PATANJALI', 'MFSL', 'ASTRAL', 'BPCL', 'ABCAPITAL', 'BANDHANBNK', 'MAHABANK', 'TATACHEM', 'SBICARD', 'ICICIPRULI', 'IDBI', 'ZYDUSLIFE', 'IDFCFIRSTB', 'HINDALCO', 'PERSISTENT', 'HAVELLS', 'SONACOMS', 'POLICYBZR', 'ZOMATO', 'DLF', 'FACT', 'POLYCAB', 'KALYANKJIL', 'APOLLOTYRE', 'YESBANK', 'INDIANB', 'JINDALSTEL', 'GMRINFRA', 'BHEL', 'IDEA', 'PEL', 'SUPREMEIND', 'KPITTECH', 'DIXON', 'SHRIRAMFIN', 'VEDL']
    else:
        tickers = ['BORORENEW', 'RAJESHEXPO', 'SUZLON', 'ASAHIINDIA', 'ZENSARTECH', 'ADANIGREEN', 'ADANIPOWER', 'GLAXO', 'RAILTEL', 'TTML', 'SOBHA', 'INOXWIND', 'FEDERALBNK', 'OBEROIRLTY', 'COCHINSHIP', 'AVANTIFEED', 'COFORGE', 'CAMS', 'SUNDRMFAST', 'OIL', 'HONAUT', 'MRF', 'ATGL', 'EICHERMOT', 'NAM-INDIA', 'TIMKEN', 'PNCINFRA', 'GRINDWELL', 'IRCON', 'NTPC', 'SUVENPHAR', 'BSE', 'TORNTPOWER', 'KPIL', 'JSWENERGY', 'LICI', 'ELGIEQUIP', 'JSWINFRA', 'HAPPYFORGE', 'DELHIVERY', 'NCC', 'TATATECH', '3MINDIA', 'PETRONET', 'KAYNES', 'ARE&M', 'ASTERDM', 'GRASIM', 'TORNTPHARM', 'ADANIENSOL', 'ISEC', 'SWANENERGY', 'PGHH', 'RAMCOCEM', 'SCHAEFFLER', 'ITC', 'SHREECEM', 'VIJAYA', 'DMART', 'JKLAKSHMI', 'MASTEK', 'APOLLOHOSP', 'CELLO', 'GODREJIND', 'SWSOLAR', 'LT', 'ULTRACEMCO', 'GODREJPROP', 'CENTURYPLY', 'SYRMA', 'HSCL', 'PPLPHARMA', 'DALBHARAT', 'ACC', 'AJANTPHARM', 'PAGEIND', 'BEML', 'JBMA', 'ZEEL', 'EIHOTEL', 'ROUTE', 'KNRCON', 'HINDUNILVR', 'TITAGARH', 'BDL', 'MEDPLUS', 'BIRLACORPN', 'VGUARD', 'RATNAMANI', 'PRESTIGE', 'TATACONSUM', 'APLLTD', 'PIDILITIND', 'NYKAA', 'HOMEFIRST', 'MARUTI', 'ASTRAZEN', 'UTIAMC', 'TEJASNET', 'GSFC', 'SIGNATURE', 'RCF', 'CONCOR', 'SUNPHARMA', 'BRIGADE', 'INDUSTOWER', 'BSOFT', 'EXIDEIND', 'GLAND', 'RAINBOW', 'PHOENIXLTD', 'DRREDDY', 'FORTIS', 'TCS', 'NH', 'RVNL', 'CESC', 'GRSE', 'ADANIPORTS', 'INFY', 'LUPIN', 'CIPLA', 'PRINCEPIPE', 'SAREGAMA', 'IRFC', 'LTTS', 'CARBORUNIV', 'MEDANTA', 'GSPL', 'KOTAKBANK', 'ADANIENT', 'SBIN', 'MPHASIS', 'LALPATHLAB', 'STARHEALTH', 'TMB', 'PRSMJOHNSN', 'ACE', 'ICICIBANK', 'CSBBANK', 'REDINGTON', 'KEI', 'UNOMINDA', 'BIKAJI', 'KIMS', 'ANURAS', 'VIPIND', 'M&M', 'CONCORDBIO', 'NUVAMA', 'CRISIL', 'AXISBANK', 'PNB', 'MAPMYINDIA', 'CREDITACC', 'IPCALAB', 'ASHOKLEY', 'IRB', 'IRCTC', 'HAPPSTMNDS', 'IOB', 'GMDCLTD', 'SUNDARMFIN', 'LLOYDSME', 'GUJGASLTD', 'NETWORK18', 'BHARATFORG', 'BATAINDIA', 'MAHLIFE', 'BAJAJ-AUTO', 'KRBL', 'DOMS', 'JBCHEPHARM', 'TRITURBINE', 'HEROMOTOCO', 'AUROPHARMA', 'ERIS', 'USHAMART', 'UNIONBANK', 'CGPOWER', 'BANKBARODA', 'MOTHERSON', 'GESHIP', 'HDFCAMC', 'JAIBALAJI', 'NSLNISP', 'CERA', 'THERMAX', 'SONATSOFTW', 'TITAN', 'GLS', 'NATCOPHARM', 'GILLETTE', 'LODHA', 'EASEMYTRIP', 'BLUESTARCO', 'AWL', 'SKFINDIA', 'ICICIGI', 'IIFL', 'CUMMINSIND', 'INDUSINDBK', 'WHIRLPOOL', 'CCL', 'GAEL', 'BBTC', 'CAPLIPOINT', 'EPL', 'LTIM', 'ALKEM', 'NESTLEIND', 'VOLTAS', 'GODREJCP', 'CGCL', 'IBULHSGFIN', 'SAPPHIRE', 'TRENT', 'POLYMED', 'MGL', 'SUNTV', 'HDFCLIFE', 'UPL', 'BALAMINES', 'KEC', 'AAVAS', 'RITES', 'ENDURANCE', 'OFSS', 'ABB', 'BAYERCROP', 'MAXHEALTH', 'PFC', 'BAJAJFINSV', 'TATAMOTORS', 'BEL', 'GAIL', 'BALKRISIND', 'NAUKRI', 'BHARTIARTL', 'JWL', 'TATAELXSI', 'MTARTECH', 'TATAMTRDVR', 'INDIACEM', 'MANKIND', 'PRAJIND', 'COLPAL', 'VAIBHAVGBL', 'TVSSCS', 'TECHM', 'TATAINVEST', 'CDSL', 'RHIM', 'CANBK', 'SRF', 'ALKYLAMINE', 'UBL', 'FINCABLES', 'CENTRALBK', 'ESCORTS', 'HEG', 'MHRIL', 'SPARC', 'RELIANCE', 'DABUR', 'BALRAMCHIN', 'AIAENG', 'INDHOTEL', 'RECLTD', 'NLCINDIA', 'POWERINDIA', 'ASIANPAINT', 'SBILIFE', 'FINPIPE', 'BAJFINANCE', 'AMBUJACEM', 'HAL', 'VTL', 'FDC', 'M&MFIN', 'KANSAINER', 'CANFINHOME', 'CHOLAHLDNG', 'IGL', 'NUVOCO', 'TRIDENT', 'NAVINFLUOR', 'TATACOMM', 'BANKINDIA', 'INDIGO', 'TRIVENI', 'POONAWALLA', 'JIOFIN', 'NMDC', 'PIIND', 'MANYAVAR', 'RBA', 'DIVISLAB', 'HUDCO', 'ANANDRATHI', 'WIPRO', 'COALINDIA', 'FSL', 'TVSMOTOR', 'MINDACORP', 'BOSCHLTD', 'BERGEPAINT', 'FLUOROCHEM', 'LICHSGFIN', 'FIVESTAR', 'RRKABEL', 'VBL', 'PNBHOUSING', 'JUBLFOOD', 'OLECTRA', 'HCLTECH', 'DATAPATTNS', 'BRITANNIA', 'CRAFTSMAN', 'GMMPFAUDLR', 'CIEINDIA', 'BAJAJHLDNG', 'GRAPHITE', 'ONGC', 'J&KBANK', 'ALLCARGO', 'PERSISTENT', 'MAZDOCK', 'HDFCBANK', 'EIDPARRY', 'HONASA', 'IOC', 'SJVN', 'MUTHOOTFIN', 'PATANJALI', 'ASTRAL', 'CHOLAFIN', 'ABFRL', 'DEEPAKNTR', 'SYNGENE', 'LINDEINDIA', 'SIEMENS', 'CLEAN', 'METROPOLIS', 'AUBANK', 'SBFC', 'QUESS', 'APLAPOLLO', 'HINDPETRO', 'ABBOTINDIA', 'DCMSHRIRAM', 'RENUKA', 'KAJARIACER', 'LXCHEM', 'TATAPOWER', 'EQUITASBNK', 'MFSL', 'AETHER', 'SBICARD', 'MARICO', 'ENGINERSIN', 'KFINTECH', 'HINDZINC', 'PAYTM', 'UJJIVANSFB', 'Time frame', 'TATASTEEL', 'POWERGRID', 'NHPC', 'RTNINDIA', 'HBLPOWER', 'JINDALSAW', 'APTUS', 'UCOBANK', 'ALOKINDS', 'WESTLIFE', 'ICICIPRULI', 'ABCAPITAL', 'ZYDUSLIFE', 'GPPL', 'HAVELLS', 'KPRMILL', 'ZFCVINDIA', 'KSB', 'JSL', 'FINEORG', 'GNFC', 'VARROC', 'SAIL', 'SANOFI', 'JSWSTEEL', 'BANDHANBNK', 'NBCC', 'TANLA', 'SHYAMMETL', 'JYOTHYLAB', 'TATACHEM', 'TIINDIA', 'LATENTVIEW', 'IEX', 'CYIENT', 'BIOCON', 'MSUMI', 'GPIL', 'LAURUSLABS', 'BPCL', 'CAMPUS', 'JUSTDIAL', 'MAHABANK', 'METROBRAND', 'CENTURYTEX', 'SOLARINDS', 'CHAMBLFERT', 'MMTC', 'APARINDS', 'POLYCAB', 'INDIAMART', 'HINDALCO', 'IDBI', 'POLICYBZR', 'MANAPPURAM', '360ONE', 'WELCORP', 'DEEPAKFERT', 'HFCL', 'WELSPUNLIV', 'STLTECH', 'ATUL', 'FACT', 'DLF', 'MOTILALOFS', 'KALYANKJIL', 'IDFCFIRSTB', 'RAYMOND', 'APOLLOTYRE', 'IDFC', 'ECLERX', 'SUNTECK', 'GLENMARK', 'BLS', 'EMAMILTD', 'LEMONTREE', 'JMFINANCIL', 'AMBER', 'MCX', 'SUMICHEM', 'SONACOMS', 'INDIGOPNTS', 'ITI', 'CUB', 'ZOMATO', 'CHALET', 'JINDALSTEL', 'RADICO', 'DEVYANI', 'YESBANK', 'AARTIIND', 'GMRINFRA', 'TV18BRDCST', 'BLUEDART', 'CHEMPLASTS', 'GRANULES', 'CEATLTD', 'INDIANB', 'SCHNEIDER', 'PEL', 'RBLBANK', 'GICRE', 'PCBL', 'CASTROLIND', 'ACI', 'COROMANDEL', 'ANGELONE', 'IDEA', 'JUBLPHARMA', 'BHEL', 'GODFRYPHLP', 'CHENNPETRO', 'JKPAPER', 'SAFARI', 'MAHSEAMLES', 'AFFLE', 'CROMPTON', 'JUBLINGREA', 'RKFORGE', 'KARURVYSYA', 'SUPREMEIND',  'KPITTECH', 'DIXON', 'SHRIRAMFIN', 'NIACL', 'INTELLECT', 'JKCEMENT', 'HINDCOPPER', 'NATIONALUM', 'PVRINOX', 'ELECON', 'MRPL', 'VEDL']   
    # Define available intervals
    interval_options = {
        '1 Minute': Interval.in_1_minute,
        '3 Minutes': Interval.in_3_minute,
        '5 Minutes': Interval.in_5_minute,
        '15 Minutes': Interval.in_15_minute,
        '30 Minutes': Interval.in_30_minute,
        '45 Minutes': Interval.in_45_minute,
        '1 Hour': Interval.in_1_hour,
        '2 Hours': Interval.in_2_hour,
        '3 Hours': Interval.in_3_hour,
        '4 Hours': Interval.in_4_hour,
        '1 Day': Interval.in_daily,
        '1 Week': Interval.in_weekly,
        '1 Month': Interval.in_monthly
    }
    max_base_candles = st.number_input('Select max_base_candles', min_value=1, max_value=6, value=3, step=1)
    user_input_zone_distance = st.number_input("Cuurent price to zone entry price distance in %", min_value=1, value=10)

    default_intervals = ['1 Minute', '3 Minutes', '5 Minutes', '15 Minutes', '30 Minutes', '1 Hour', '2 Hours', '1 Day', '1 Week']
    # Multi-select for intervals with all options as default
    selected_intervals = st.multiselect('Select Time Intervals', list(interval_options.keys()), default=default_intervals)
    refresh_time = min([refresh_period[interval] for interval in selected_intervals])


    # Retrieve the corresponding interval objects
    intervals = [interval_options[interval] for interval in selected_intervals]

    # Determine high time frame (htf) intervals based on selected intervals
    htf_intervals = []
    for selected_interval in selected_intervals:
        if selected_interval == '1 Minute':
            htf_intervals.append(Interval.in_15_minute)
        elif selected_interval in ['3 Minutes', '5 Minutes']:
            htf_intervals.append(Interval.in_1_hour)
        elif selected_interval == '15 Minutes':
            htf_intervals.append(Interval.in_daily)
        elif selected_interval in ['1 Hour', '2 Hours']:
            htf_intervals.append(Interval.in_weekly)
        elif selected_interval == '1 Day':
            htf_intervals.append(Interval.in_monthly)
        else:
            htf_intervals.append(None)  # Default case, if needed
            
    reward_value = 3 if any(interval in (Interval.in_3_minute, Interval.in_5_minute) for interval in intervals) else 5

    nse = mcal.get_calendar('NSE')

    # Get today's date
    end_date = datetime.now()

    days_back = st.slider('Select Scan period days', min_value=1, max_value=5000, value=365)

    # Calculate the start date based on the selected number of days
    start_date = end_date - timedelta(days=days_back)

    # Get the trading days in the specified range
    trading_days = nse.schedule(start_date=start_date, end_date=end_date)

    # Define candles for each time frame
    candles_count = {
        '1 Minute': 375,
        '3 Minutes': 125,
        '5 Minutes': 75,
        '10 Minutes': 38,
        '15 Minutes': 25,
        '30 Minutes': 13,
        '45 Minutes': 8,  # Approximation
        '1 Hour': 7,
        '2 Hours': 4,
        '3 Hours': 2,
        '4 Hours': 1,
        '1 Day': 1,
        '1 Week': 5,
        '1 Month': 20,
    }

    st.write("Select zone status type to scan")    
    zone_status_checks = st.columns(3)
    with zone_status_checks[0]:
        fresh_zone_allowed = st.checkbox("Fresh Zone")
    with zone_status_checks[1]:
        target_zone_allowed = st.checkbox("Target Zone")
    with zone_status_checks[2]:
        stoploss_zone_allowed = st.checkbox("Stoploss Zone")
    
    st.write("Select zone type to scan")
    zone_type_checks = st.columns(2)
    with zone_type_checks[0]:
        scan_demand_zone_allowed = st.checkbox("Scan Demand")
    with zone_type_checks[1]:
        scan_supply_zone_allowed = st.checkbox("Scan Supply")
        
    if auto_refresh:
    st.write(f"Auto-refresh enabled for every {refresh_time / 60:.0f} minutes.")
    
    while True:
        # Fetch stock data and scan zones
        patterns_found = find_patterns(...)
        st.dataframe(patterns_found)
        
        # Refresh after selected interval
        time.sleep(refresh_time)
else:
    patterns_found = find_patterns(...)
    st.dataframe(patterns_found)


all_patterns = []

if find_patterns_button:
    patterns_found_button_clicked = True
    progress_bar = st.progress(0)
    progress_text = st.empty()
    progress_percent = 0
    start_time = time.time()
    patterns_found = []
    any_patterns_found = False  # Initialize the flag

    for i, ticker in enumerate(tickers):
        progress_percent = (i + 1) / len(tickers)
        progress_bar.progress(progress_percent)
        progress_text.text(f"🔍 Scanning Zone for {ticker}: {i + 1} of {len(tickers)} Stocks Analyzed")

        for idx, interval in enumerate(intervals):
            try:
                # Get the number of candles for the selected interval
                candles_in_selected_time_frame = candles_count[selected_intervals[idx]]
                    
                # Get the count of trading days
                trading_days_count = len(trading_days)

                # Calculate the total number of candles
                n_bar = trading_days_count * candles_in_selected_time_frame

                # Fetch historical data using tvDatafeed
                stock_data = tv.get_hist(symbol=ticker, exchange='NSE', interval=interval, n_bars=n_bar)
                
                # Get the corresponding htf_interval based on the current index
                htf_interval = htf_intervals[idx] if idx < len(htf_intervals) else None
                    
                # Download stock data for the higher timeframe
                stock_data_htf = tv.get_hist(symbol=ticker, exchange='NSE', interval=htf_interval, n_bars=2000) if htf_interval else None

                # Check if stock_data_htf is not None
                if stock_data_htf is not None:
                    # Rename columns to match expected names
                    stock_data_htf.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'}, inplace=True)
                    # Localize and convert the index to the desired timezone
                    stock_data_htf.index = stock_data_htf.index.tz_localize('UTC').tz_convert('Asia/Kolkata')
                    # Round the values to 2 decimal places
                    stock_data_htf = stock_data_htf.round(2)

                # Check if stock_data is None
                if stock_data is not None:
                    stock_data.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'}, inplace=True)
                    stock_data.index = stock_data.index.tz_localize('UTC').tz_convert('Asia/Kolkata')
                    stock_data = stock_data.round(2)

                    stock_data = calculate_atr(stock_data)  # Assuming calculate_atr is defined elsewhere
                    interval = selected_intervals[idx]
                    patterns = find_patterns(ticker, stock_data, stock_data_htf, interval, max_base_candles, scan_demand_zone_allowed, scan_supply_zone_allowed, reward_value, fresh_zone_allowed, target_zone_allowed, stoploss_zone_allowed, htf_interval,user_input_zone_distance)  # Assuming find_patterns is defined elsewhere    
            except Exception:
                 continue  # Handle exceptions as needed
            if patterns:
               any_patterns_found = True  # Set the flag if patterns are found
               all_patterns.extend(patterns)
    progress_bar.progress(1.0)
    if all_patterns:
        my_patterns_df = pd.DataFrame(all_patterns)
        my_patterns_df = my_patterns_df.drop_duplicates(subset=['Entry_Price', 'Stop_loss'], keep=False)

        patterns_df = my_patterns_df.sort_values(by='Zone_Distance', ascending=True).reset_index(drop=True)

        # Add '%' suffix to each row in the Zone_Distance column
        patterns_df['Zone_Distance'] = patterns_df['Zone_Distance'].astype(str) + ' %'

        patterns_df['Exit_index'] = patterns_df['Exit_index'].fillna(0)
        patterns_df['Entry_index'] = patterns_df['Entry_index'].fillna(0)

        # Calculate Time_in_Trade and add " candles" suffix directly
        patterns_df['Time_in_Trade'] = (patterns_df['Exit_index'] - patterns_df['Entry_index']).astype(int).astype(str) + ' candles'

        cols = list(patterns_df.columns)  # Get the current columns
        exit_date_index = cols.index('Exit_date')  # Find the index of Exit_date

        # Insert Time_in_Trade right after Exit_date
        if 'Time_in_Trade' in cols:
            cols.insert(exit_date_index + 1, cols.pop(cols.index('Time_in_Trade')))

        # Reassign the columns in the desired order
        patterns_df = patterns_df[cols]

        # Calculate and display elapsed time
        end_time = time.time()
        elapsed_time = end_time - start_time
        st.success(f"🔍 Scanning completed in {elapsed_time:.2f} seconds for {days_back} calendar days, which have {trading_days_count} trading days.")

        patterns_df['Pulse_and_trend'] = patterns_df['Pulse_details'] + patterns_df['Trend']
        
        # Function to process the DataFrame for a given Zone_Type prefix
        def process_zone_type(zone_type_prefix):
            global total_fresh_zone_count, total_target_zone_count, total_stoploss_zone_count
            # Filter the DataFrame for the specified Zone_Type
            filtered_df = patterns_df[patterns_df['Zone_Type'].str.startswith(zone_type_prefix)]
            
            # Count occurrences of "Target", "Stop loss", and "Fresh" for each unique Pulse_and_trend value
            result = filtered_df.groupby('Pulse_and_trend')['Zone_status'].value_counts().unstack(fill_value=0)

            # Initialize counts to zero
            Fresh_zone_count = 0
            Target_zone_count = 0
            StopLoss_zone_count = 0
            
            # Check if the expected columns exist in the result
            if 'Fresh' in result.columns:
                Fresh_zone_count = result['Fresh'].sum()
            if 'Target' in result.columns:
                Target_zone_count = result['Target'].sum()
            if 'Stop loss' in result.columns:
                StopLoss_zone_count = result['Stop loss'].sum()

    
            # Print total counts
            st.write(f"Total {zone_type_prefix} Target: {Target_zone_count}")
            st.write(f"Total {zone_type_prefix} Stop loss: {StopLoss_zone_count}") 
            st.write(f"Total {zone_type_prefix} Fresh: {Fresh_zone_count}")

            # Print the filtered result
            st.dataframe(result)

        # Process both DZ and SZ Zone_Types
        tab1, tab2 = st.tabs(["📁 DZ Data", "📁 SZ Data"])

        with tab1:        
            if 'DZ(RBR)' in patterns_df['Zone_Type'].unique() or 'DZ(DBR)' in patterns_df['Zone_Type'].unique():
               process_zone_type('DZ')

        with tab2:
           if 'SZ(DBD)' in patterns_df['Zone_Type'].unique() or 'SZ(RBD)' in patterns_df['Zone_Type'].unique():
              process_zone_type('SZ')

        Fresh_zone_count = patterns_df['Zone_status'].value_counts().get('Fresh', 0)
        Target_zone_count = patterns_df['Zone_status'].value_counts().get('Target', 0)
        StopLoss_zone_count = patterns_df['Zone_status'].value_counts().get('Stop loss', 0)
        Total_zone = Fresh_zone_count + Target_zone_count + StopLoss_zone_count
        
        st.write(f"**Total zone_count:** {Total_zone}")        
        st.markdown(f"  - **Fresh_zone_count:** {Fresh_zone_count}")
        st.markdown(f"  - **Target_hit_count:** {Target_zone_count}")
        st.markdown(f"  - **Stoploss_zone_count:** {StopLoss_zone_count}")
        
        tab1, tab2 = st.tabs([ "📁 Data","📈 Chart"])
        with tab1:
            st.markdown("**Table View**")
            st.dataframe(patterns_df.drop(columns=['OHLC_Data','Close_price','Exit_index','Entry_index','Pulse_and_trend'], errors='ignore'))
    
        with tab2:
            st.markdown("**Chart View**")
            if not patterns_df.empty:
                for index, row in patterns_df.iterrows():
                    ticker_name = row['Symbol']
                    ohlc_data = row['OHLC_Data']
                    legin_date = row['legin_date']  # Ensure these fields exist in your DataFrame
                    legout_date = row['legout_date']
                    base_count = row['base_count']
                    Entry_Price = row['Entry_Price']
                    Stop_loss = row['Stop_loss']
                    Minimum_target = round(row['Target'],2)
                    ltf_time_frame = row['Time frame']  # Make sure 'interval' is defined
                    pattern_name = row['Zone_Type']  
                    pulse_details   = row['Pulse_details']
                    trend = row['Trend']
                    Zone_status = row['Zone_status']
                    eod_close = row['Close_price']

                    # Filter out non-trading dates
                    ohlc_data = ohlc_data.dropna(subset=['Open', 'High', 'Low', 'Close'])

                    hover_text = [
                        f"Open: {row['Open']}<br>" +
                        f"High: {row['High']}<br>" +
                        f"Low: {row['Low']}<br>" +
                        f"Close: {row['Close']}<br>" +
                        f"TR: {row['TR']}<br>" +
                        f"ATR: {row['ATR']}<br>" +
                        f"Body: {row['Candle_Body']}<br>" +
                        f"Range: {row['Candle_Range']}"
                        for _, row in ohlc_data.iterrows()
                    ]

                    # Create a candlestick chart
                    fig = go.Figure(data=[go.Candlestick(
                        x=ohlc_data.index,
                        open=ohlc_data['Open'],
                        high=ohlc_data['High'],
                        low=ohlc_data['Low'],
                        close=ohlc_data['Close'],
                        name=ticker_name,
                        increasing_line_color='#26a69a',  # Set increasing line color
                        decreasing_line_color='#ef5350',  # Set decreasing line color
                        increasing_fillcolor='#26a69a',   # Set increasing fill color
                        decreasing_fillcolor='#ef5350',   # Set decreasing fill color
                        line_width=1,  # Set line thickness
                        hovertext=hover_text,  # Set custom hover text
                        hoverinfo='text'  # Show only custom hover text
                    )])
                    try:
                        legout_candle_index = ohlc_data.index.get_loc(legout_date)
                    except KeyError:
                        legout_candle_index = None  # Handle the case where legout_date is not found

                    # Determine shape_start based on legin_date
                    try:
                        shape_start = ohlc_data.index[ohlc_data.index.get_loc(legin_date)]
                    except KeyError:
                        if legout_candle_index is not None:
                            shape_start = legout_candle_index - base_count
                        else:
                            shape_start = None  # Handle the case where both dates are not found

                    shape_end = ohlc_data.index[-1]

                    # Add the rectangle shape based on pattern type
                    if pattern_name in ['DZ(RBR)', 'DZ(DBR)']:
                        fill_color = "green"
                    elif pattern_name in ['SZ(DBD)', 'SZ(RBD)']:
                        fill_color = "red"

                    # Add the rectangle shape if shape_start is valid
                    if shape_start is not None:
                        fig.add_shape(
                            type="rect",
                            xref="x",
                            yref="y",
                            x0=shape_start,
                            y0=Stop_loss,
                            x1=shape_end,
                            y1=Entry_Price,
                            fillcolor=fill_color,
                            opacity=0.2,
                            layer="below",
                            line=dict(width=0),
                        )                    
                    # Add a horizontal line for Minimum_target
                    fig.add_shape(
                        type="line",
                        x0=ohlc_data.index[0],  # Start at the first index of the OHLC data
                        y0=Minimum_target,
                        x1=shape_end,
                        y1=Minimum_target,
                        line=dict(color="lightgreen", width=2, dash="dash"),  # Set color to light green
                    )
                    # Add Target text label
                    fig.add_annotation(
                        x=shape_end,  # Position the label at shape_end
                        y=Minimum_target,  # Align with the Minimum_target line
                        text=f'Target: ₹ {Minimum_target}',  # Text for the label
                        showarrow=True,
                        arrowhead=2,
                        ax=-10,  # Adjust x position
                        ay=-10,  # Adjust y position
                        font=dict(size=10, color='black'),
                        bgcolor='white',
                        bordercolor='lightgreen',
                        borderwidth=1,
                        borderpad=4
                    )                    
                    if pattern_name in ['SZ(RBD)', 'SZ(DBD)']:                    
                       fixed_distance = 0.5  # Adjust this value as needed
                       # Add text annotations for Entry_Price and Stop_loss
                       fig.add_annotation(
                           x=shape_end,
                           y=Stop_loss + fixed_distance,
                           text=f'Stop Loss: ₹ {Stop_loss}',
                           showarrow=True,
                           arrowhead=2,
                           ax=10,
                           ay=-10,
                           font=dict(size=10, color='black'),
                           bgcolor='white',
                           bordercolor='red',  # Added border color for better contrast
                           borderwidth=1,  # Added border width
                           borderpad=4                        
                       )

                       fig.add_annotation(
                           x=shape_end,
                           y=Entry_Price,
                           text=f'Entry: ₹ {Entry_Price}',
                           showarrow=True,
                           arrowhead=2,
                           ax=10,
                           ay=10,
                           font=dict(size=10, color='black'),
                           bgcolor='white',
                           bordercolor='green',  # Added border color for better contrast
                           borderwidth=1,  # Added border width
                           borderpad=4                        
                        
                       )
                    else:
                       fixed_distance = 0.5  # Adjust this value as needed
                       # Add text annotations for Entry_Price and Stop_loss
                       fig.add_annotation(
                           x=shape_end,
                           y=Entry_Price,
                           text=f'Entry: ₹ {Entry_Price}',
                           showarrow=True,
                           arrowhead=2,
                           ax=10,
                           ay=-10,
                           font=dict(size=10, color='black'),
                           bgcolor='white',
                           bordercolor='green',  # Added border color for better contrast
                           borderwidth=1,  # Added border width
                           borderpad=4                        
                       )

                       fig.add_annotation(
                           x=shape_end,
                           y=Stop_loss + fixed_distance,
                           text=f'Stop Loss: ₹ {Stop_loss}',
                           showarrow=True,
                           arrowhead=2,
                           ax=10,
                           ay=10,
                           font=dict(size=10, color='black'),
                           bgcolor='white',
                           bordercolor='red',  # Added border color for better contrast
                           borderwidth=1,  # Added border width
                           borderpad=4                        
                        
                       )    
                    
                    # Update layout to remove datetime from x-axis and enhance the chart
                    fig.update_layout(
                        title = (
                            f'Chart: {ticker_name} ⎜ '
                            f'{ltf_time_frame} ⎜'                            
                            f'<span>{pattern_name} ⎜</span> '
                            f'<span>{pulse_details} ⎜</span> '
                            f'<span>Trend:{trend} ⎜</span> '
                            f'<span>Zone_status:{Zone_status}</span>'
                        ),
                        title_x=0.5,  # Center the title
                        title_xanchor='center',  # Anchor the title to the center
                        yaxis_title='Price',
                        xaxis_rangeslider_visible=False,  # Hide the range slider
                        xaxis_showgrid=False,  # Disable grid for cleaner look
                        margin=dict(l=0, r=0, t=100, b=40),  # Adjust margins
                        height=600,  # Set height for better presentation
                        width=800,   # Set width for better presentation
                        xaxis=dict(
                            type='category',  # Set x-axis to category to avoid gaps
                            tickvals=[],  # Clear tick values to stop displaying dates
                            ticktext=[],  # Clear tick text to stop displaying dates
                            fixedrange=False,  # Disable zooming on x-axis
                            range=[0, 24],
                            autorange=True
                        ),
                        yaxis=dict(
                            autorange=True,
                            fixedrange=True  # Disable zooming on y-axis
                        ),
                        dragmode='pan'  # Enable panning mode                  
                    )

                    # Add styled header annotation with increased y position
                    header_text = (
                        f"<span style='padding-right: 20px;'><b>👉 Legin Date:</b> {legin_date}</span>"
                        f"<span style='padding-right: 20px;'><b>👉 Base Count:</b> {base_count}</span>"
                        f"<span style='padding-right: 20px;'><b>👉 Legout Date:</b> {legout_date}</span>"                 
                       
                    )

                    fig.add_annotation(
                        x=0.5,
                        y=1.1,  # Increased y position for more space
                        text=header_text,
                        showarrow=False,
                        align='center', 
                        xref='paper',
                        yref='paper',
                        font=dict(size=14, color='black'),
                        bgcolor='rgba(255, 255, 255, 0.8)',  # Light background for header
                        borderpad=4,
                        width=800,
                        height=50,
                        valign='middle'
                    )
                            
                    # Display the chart in Streamlit 
                    st.plotly_chart(fig)
                    if (index + 1) % 5 == 0:
                        time.sleep(5)  # Sleep for 5 seconds                    

    else:
        st.info("No patterns found for the selected tickers and intervals.")
            
    progress_bar.empty()
    progress_text.empty()
    
