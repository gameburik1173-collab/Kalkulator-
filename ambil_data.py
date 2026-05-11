"""
=============================================================================
AMBIL DATA - Multi-Timeframe Data Handler
=============================================================================
Handles data retrieval for M1, M3, M5, M15 timeframes
Calculates indicators: EMA, ATR, Volume Profile, Swing Points
=============================================================================
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import logging

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

from config import (
    BROKER_CONFIG, TIMEFRAMES, CANDLE_COUNT,
    MTF_CONFIG, SR_CONFIG, BREAKOUT_CONFIG
)

logger = logging.getLogger(__name__)


# ===================== TIMEFRAME MAPPING =====================
TF_MAP = {
    "M1": mt5.TIMEFRAME_M1 if MT5_AVAILABLE else 1,
    "M3": mt5.TIMEFRAME_M3 if MT5_AVAILABLE else 3,
    "M5": mt5.TIMEFRAME_M5 if MT5_AVAILABLE else 5,
    "M15": mt5.TIMEFRAME_M15 if MT5_AVAILABLE else 15,
    "M30": mt5.TIMEFRAME_M30 if MT5_AVAILABLE else 30,
    "H1": mt5.TIMEFRAME_H1 if MT5_AVAILABLE else 60,
    "H4": mt5.TIMEFRAME_H4 if MT5_AVAILABLE else 240,
    "D1": mt5.TIMEFRAME_D1 if MT5_AVAILABLE else 1440,
}


class DataHandler:
    """
    Multi-timeframe data handler.
    Fetches and processes OHLCV data from MT5 for multiple timeframes.
    """

    def __init__(self, symbol=None):
        self.symbol = symbol or BROKER_CONFIG["symbol"]
        self.data = {}  # Dict of DataFrames per timeframe
        self.indicators = {}  # Calculated indicators per timeframe
        self.sr_levels = []  # Support/Resistance levels
        self.swing_points = []  # Swing highs and lows
        self.connected = False

    # ===================== CONNECTION =====================
    def connect(self):
        """Initialize MT5 connection."""
        if not MT5_AVAILABLE:
            logger.error("MetaTrader5 not installed. Install with: pip install MetaTrader5")
            return False

        if not mt5.initialize():
            logger.error(f"MT5 initialization failed: {mt5.last_error()}")
            return False

        # Login if credentials provided
        if BROKER_CONFIG["login"] > 0:
            authorized = mt5.login(
                login=BROKER_CONFIG["login"],
                password=BROKER_CONFIG["password"],
                server=BROKER_CONFIG["server"]
            )
            if not authorized:
                logger.error(f"MT5 login failed: {mt5.last_error()}")
                return False

        self.connected = True
        logger.info(f"Connected to MT5. Symbol: {self.symbol}")
        return True

    def disconnect(self):
        """Shutdown MT5 connection."""
        if MT5_AVAILABLE and self.connected:
            mt5.shutdown()
            self.connected = False
            logger.info("Disconnected from MT5")

    # ===================== DATA FETCHING =====================
    def fetch_all_timeframes(self):
        """Fetch data for all configured timeframes."""
        success = True
        for tf_name, tf_label in TIMEFRAMES.items():
            count = CANDLE_COUNT.get(tf_label, 200)
            df = self.fetch_candles(tf_label, count)
            if df is not None and not df.empty:
                self.data[tf_label] = df
                self._calculate_indicators(tf_label)
                logger.info(f"Fetched {len(df)} candles for {tf_label}")
            else:
                logger.warning(f"Failed to fetch data for {tf_label}")
                success = False
        return success

    def fetch_candles(self, timeframe, count=200):
        """
        Fetch OHLCV candles from MT5.

        Args:
            timeframe: String timeframe (M1, M5, M15, etc.)
            count: Number of candles to fetch

        Returns:
            DataFrame with OHLCV + time columns
        """
        if not self.connected:
            logger.error("Not connected to MT5")
            return None

        tf_mt5 = TF_MAP.get(timeframe)
        if tf_mt5 is None:
            logger.error(f"Invalid timeframe: {timeframe}")
            return None

        try:
            rates = mt5.copy_rates_from_pos(self.symbol, tf_mt5, 0, count)
            if rates is None or len(rates) == 0:
                logger.error(f"No data received for {timeframe}")
                return None

            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)

            # Rename columns for consistency
            df.rename(columns={
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'tick_volume': 'volume',
                'real_volume': 'real_volume',
                'spread': 'spread'
            }, inplace=True)

            # Calculate basic derived columns
            df['body'] = abs(df['close'] - df['open'])
            df['range'] = df['high'] - df['low']
            df['body_ratio'] = df['body'] / df['range'].replace(0, np.nan)
            df['is_bullish'] = df['close'] > df['open']
            df['mid_price'] = (df['high'] + df['low']) / 2

            return df

        except Exception as e:
            logger.error(f"Error fetching {timeframe} data: {e}")
            return None

    def get_current_price(self):
        """Get current bid/ask price."""
        if not self.connected:
            return None, None

        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return None, None
        return tick.bid, tick.ask

    def get_symbol_info(self):
        """Get symbol information (point, digits, etc.)."""
        if not self.connected:
            return None
        return mt5.symbol_info(self.symbol)


    # ===================== INDICATORS =====================
    def _calculate_indicators(self, timeframe):
        """Calculate all indicators for a timeframe."""
        df = self.data.get(timeframe)
        if df is None or df.empty:
            return

        indicators = {}

        # EMA calculations
        indicators['ema_fast'] = self._ema(df['close'], MTF_CONFIG['trend_ema_fast'])
        indicators['ema_slow'] = self._ema(df['close'], MTF_CONFIG['trend_ema_slow'])
        indicators['ema_200'] = self._ema(df['close'], MTF_CONFIG['trend_ema_filter'])
        indicators['ema_signal'] = self._ema(df['close'], MTF_CONFIG['signal_ema'])
        indicators['ema_micro'] = self._ema(df['close'], MTF_CONFIG['micro_ema'])

        # ATR (Average True Range)
        indicators['atr'] = self._atr(df, period=14)

        # Volume analysis
        indicators['vol_sma'] = df['volume'].rolling(window=20).mean()
        indicators['vol_ratio'] = df['volume'] / indicators['vol_sma']

        # Momentum (ROC - Rate of Change)
        indicators['momentum'] = df['close'].pct_change(periods=10) * 100

        # RSI
        indicators['rsi'] = self._rsi(df['close'], period=14)

        # Volatility (standard deviation of returns)
        indicators['volatility'] = df['close'].pct_change().rolling(window=20).std()

        # Trend strength (ADX simplified)
        indicators['trend_strength'] = self._trend_strength(df)

        # Store in indicators dict
        self.indicators[timeframe] = indicators

        # Also add indicators to the DataFrame
        for key, value in indicators.items():
            if isinstance(value, pd.Series):
                df[key] = value

    def _ema(self, series, period):
        """Calculate Exponential Moving Average."""
        return series.ewm(span=period, adjust=False).mean()

    def _atr(self, df, period=14):
        """Calculate Average True Range."""
        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr

    def _rsi(self, series, period=14):
        """Calculate RSI."""
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)

        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _trend_strength(self, df, period=14):
        """
        Simplified trend strength calculation (0-1).
        Based on directional movement.
        """
        high = df['high']
        low = df['low']

        plus_dm = high.diff()
        minus_dm = -low.diff()

        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

        atr = self._atr(df, period)

        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr.replace(0, np.nan))
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr.replace(0, np.nan))

        dx = abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan) * 100
        adx = dx.rolling(window=period).mean()

        # Normalize to 0-1
        return (adx / 100).clip(0, 1)


    # ===================== SUPPORT & RESISTANCE =====================
    def calculate_sr_levels(self, timeframe="M5"):
        """
        Calculate Support and Resistance levels using fractal method.
        Returns list of SR levels with strength scores.
        """
        df = self.data.get(timeframe)
        if df is None or df.empty:
            return []

        period = SR_CONFIG["fractal_period"]
        levels = []

        # Find fractal highs (resistance)
        for i in range(period, len(df) - period):
            is_fractal_high = True
            is_fractal_low = True

            for j in range(1, period + 1):
                if df['high'].iloc[i] <= df['high'].iloc[i - j]:
                    is_fractal_high = False
                if df['high'].iloc[i] <= df['high'].iloc[i + j]:
                    is_fractal_high = False
                if df['low'].iloc[i] >= df['low'].iloc[i - j]:
                    is_fractal_low = False
                if df['low'].iloc[i] >= df['low'].iloc[i + j]:
                    is_fractal_low = False

            if is_fractal_high:
                levels.append({
                    'price': df['high'].iloc[i],
                    'type': 'resistance',
                    'time': df.index[i],
                    'index': i
                })

            if is_fractal_low:
                levels.append({
                    'price': df['low'].iloc[i],
                    'type': 'support',
                    'time': df.index[i],
                    'index': i
                })

        # Cluster nearby levels
        clustered = self._cluster_sr_levels(levels)

        # Calculate strength for each level
        for level in clustered:
            level['strength'] = self._calculate_sr_strength(level, df)

        # Sort by strength
        clustered.sort(key=lambda x: x['strength'], reverse=True)

        self.sr_levels = clustered
        logger.info(f"Found {len(clustered)} SR levels on {timeframe}")
        return clustered

    def _cluster_sr_levels(self, levels):
        """Cluster nearby SR levels together."""
        if not levels:
            return []

        threshold = SR_CONFIG["cluster_threshold_pips"] * self._get_pip_value()
        clustered = []

        # Sort by price
        sorted_levels = sorted(levels, key=lambda x: x['price'])

        current_cluster = [sorted_levels[0]]

        for i in range(1, len(sorted_levels)):
            if sorted_levels[i]['price'] - current_cluster[-1]['price'] <= threshold:
                current_cluster.append(sorted_levels[i])
            else:
                # Average the cluster
                avg_price = np.mean([l['price'] for l in current_cluster])
                clustered.append({
                    'price': avg_price,
                    'type': current_cluster[0]['type'],
                    'touches': len(current_cluster),
                    'first_time': current_cluster[0]['time'],
                    'last_time': current_cluster[-1]['time'],
                })
                current_cluster = [sorted_levels[i]]

        # Don't forget last cluster
        if current_cluster:
            avg_price = np.mean([l['price'] for l in current_cluster])
            clustered.append({
                'price': avg_price,
                'type': current_cluster[0]['type'],
                'touches': len(current_cluster),
                'first_time': current_cluster[0]['time'],
                'last_time': current_cluster[-1]['time'],
            })

        return clustered

    def _calculate_sr_strength(self, level, df):
        """
        Calculate strength of an SR level (0-1).
        Based on: touches, recency, volume at level.
        """
        weights = SR_CONFIG["sr_strength_weight"]

        # Touch score (normalized)
        touch_score = min(level.get('touches', 1) / 5.0, 1.0)

        # Recency score
        if 'last_time' in level and len(df) > 0:
            total_time = (df.index[-1] - df.index[0]).total_seconds()
            level_age = (df.index[-1] - level['last_time']).total_seconds()
            recency_score = max(0, 1.0 - (level_age / total_time)) if total_time > 0 else 0.5
        else:
            recency_score = 0.5

        # Volume score (average volume near level)
        pip_value = self._get_pip_value()
        near_level = df[abs(df['close'] - level['price']) < 10 * pip_value]
        if len(near_level) > 0 and 'vol_sma' in df.columns:
            vol_at_level = near_level['volume'].mean()
            vol_avg = df['volume'].mean()
            volume_score = min(vol_at_level / vol_avg if vol_avg > 0 else 0.5, 2.0) / 2.0
        else:
            volume_score = 0.5

        # Weighted score
        strength = (
            weights['touches'] * touch_score +
            weights['recency'] * recency_score +
            weights['volume'] * volume_score
        )

        return min(max(strength, 0), 1.0)

    def _get_pip_value(self):
        """Get pip value for the symbol."""
        symbol_upper = self.symbol.upper()
        if "XAUUSD" in symbol_upper or "GOLD" in symbol_upper:
            return 0.1  # Gold: 1 pip = 0.1 (termasuk XAUUSDm, XAUUSD., dll)
        elif "JPY" in symbol_upper:
            return 0.01
        else:
            return 0.0001  # Standard forex pairs


    # ===================== SWING POINTS =====================
    def find_swing_points(self, timeframe="M5"):
        """
        Find swing highs and swing lows for pattern detection.
        Used by QM pattern detector.
        """
        df = self.data.get(timeframe)
        if df is None or df.empty:
            return []

        lookback = 5
        swings = []

        for i in range(lookback, len(df) - lookback):
            # Swing High
            is_swing_high = all(
                df['high'].iloc[i] > df['high'].iloc[i - j] and
                df['high'].iloc[i] > df['high'].iloc[i + j]
                for j in range(1, lookback + 1)
            )

            # Swing Low
            is_swing_low = all(
                df['low'].iloc[i] < df['low'].iloc[i - j] and
                df['low'].iloc[i] < df['low'].iloc[i + j]
                for j in range(1, lookback + 1)
            )

            if is_swing_high:
                swings.append({
                    'type': 'high',
                    'price': df['high'].iloc[i],
                    'time': df.index[i],
                    'index': i,
                })

            if is_swing_low:
                swings.append({
                    'type': 'low',
                    'price': df['low'].iloc[i],
                    'time': df.index[i],
                    'index': i,
                })

        # Sort by index
        swings.sort(key=lambda x: x['index'])
        self.swing_points = swings
        return swings

    # ===================== TREND ANALYSIS =====================
    def get_trend_direction(self, timeframe="M15"):
        """
        Determine trend direction on specified timeframe.

        Returns:
            dict: {
                'direction': 'bullish' | 'bearish' | 'neutral',
                'strength': 0.0 - 1.0,
                'ema_position': 'above' | 'below',
                'higher_highs': bool,
                'higher_lows': bool
            }
        """
        df = self.data.get(timeframe)
        if df is None or df.empty:
            return {'direction': 'neutral', 'strength': 0}

        indicators = self.indicators.get(timeframe, {})
        current_close = df['close'].iloc[-1]

        # EMA position
        ema_fast = indicators.get('ema_fast')
        ema_slow = indicators.get('ema_slow')
        ema_200 = indicators.get('ema_200')

        ema_bullish = False
        ema_bearish = False

        if ema_fast is not None and ema_slow is not None:
            ema_bullish = (
                ema_fast.iloc[-1] > ema_slow.iloc[-1] and
                current_close > ema_fast.iloc[-1]
            )
            ema_bearish = (
                ema_fast.iloc[-1] < ema_slow.iloc[-1] and
                current_close < ema_fast.iloc[-1]
            )

        above_200 = current_close > ema_200.iloc[-1] if ema_200 is not None and len(ema_200) > 0 else None

        # Higher Highs / Higher Lows check
        swings = self.find_swing_points(timeframe)
        recent_highs = [s for s in swings[-10:] if s['type'] == 'high']
        recent_lows = [s for s in swings[-10:] if s['type'] == 'low']

        higher_highs = False
        higher_lows = False
        lower_highs = False
        lower_lows = False

        if len(recent_highs) >= 2:
            higher_highs = recent_highs[-1]['price'] > recent_highs[-2]['price']
            lower_highs = recent_highs[-1]['price'] < recent_highs[-2]['price']

        if len(recent_lows) >= 2:
            higher_lows = recent_lows[-1]['price'] > recent_lows[-2]['price']
            lower_lows = recent_lows[-1]['price'] < recent_lows[-2]['price']

        # Determine direction
        bullish_score = 0
        bearish_score = 0

        if ema_bullish:
            bullish_score += 1
        if ema_bearish:
            bearish_score += 1
        if above_200:
            bullish_score += 1
        elif above_200 is False:
            bearish_score += 1
        if higher_highs:
            bullish_score += 1
        if higher_lows:
            bullish_score += 1
        if lower_highs:
            bearish_score += 1
        if lower_lows:
            bearish_score += 1

        # Get trend strength from ADX
        trend_str = indicators.get('trend_strength')
        strength = trend_str.iloc[-1] if trend_str is not None and len(trend_str) > 0 else 0.5

        if bullish_score > bearish_score:
            direction = 'bullish'
        elif bearish_score > bullish_score:
            direction = 'bearish'
        else:
            direction = 'neutral'

        return {
            'direction': direction,
            'strength': float(strength) if not np.isnan(strength) else 0.5,
            'ema_position': 'above' if ema_bullish else ('below' if ema_bearish else 'neutral'),
            'higher_highs': higher_highs,
            'higher_lows': higher_lows,
            'lower_highs': lower_highs,
            'lower_lows': lower_lows,
            'above_ema200': above_200,
            'bullish_score': bullish_score,
            'bearish_score': bearish_score,
        }

    # ===================== MARKET CONDITIONS =====================
    def get_market_condition(self, timeframe="M5"):
        """
        Analyze current market condition.

        Returns:
            dict with volatility, session, market type (trending/ranging)
        """
        df = self.data.get(timeframe)
        if df is None or df.empty:
            return {}

        indicators = self.indicators.get(timeframe, {})

        # Current ATR
        atr = indicators.get('atr')
        current_atr = atr.iloc[-1] if atr is not None and len(atr) > 0 else 0

        # Volatility assessment
        volatility = indicators.get('volatility')
        current_vol = volatility.iloc[-1] if volatility is not None and len(volatility) > 0 else 0

        # Average ATR for comparison
        avg_atr = atr.mean() if atr is not None else current_atr

        # Market type
        trend_strength = indicators.get('trend_strength')
        ts_val = trend_strength.iloc[-1] if trend_strength is not None and len(trend_strength) > 0 else 0.3

        if ts_val > 0.5:
            market_type = "trending"
        elif ts_val > 0.25:
            market_type = "weak_trend"
        else:
            market_type = "ranging"

        # Volatility level
        if avg_atr > 0:
            vol_ratio = current_atr / avg_atr
            if vol_ratio > 1.5:
                vol_level = "high"
            elif vol_ratio > 0.8:
                vol_level = "normal"
            else:
                vol_level = "low"
        else:
            vol_level = "normal"

        # Current session
        now = datetime.utcnow()
        hour = now.hour
        if 0 <= hour < 8:
            session = "asian"
        elif 8 <= hour < 13:
            session = "london"
        elif 13 <= hour < 16:
            session = "overlap"
        elif 16 <= hour < 21:
            session = "newyork"
        else:
            session = "off_hours"

        return {
            'market_type': market_type,
            'volatility_level': vol_level,
            'current_atr': float(current_atr) if not np.isnan(current_atr) else 0,
            'avg_atr': float(avg_atr) if not np.isnan(avg_atr) else 0,
            'session': session,
            'trend_strength': float(ts_val) if not np.isnan(ts_val) else 0,
            'hour_utc': hour,
        }

    # ===================== UTILITY =====================
    def get_latest_candles(self, timeframe, count=5):
        """Get the latest N candles for a timeframe."""
        df = self.data.get(timeframe)
        if df is None or df.empty:
            return None
        return df.tail(count)

    def get_data(self, timeframe):
        """Get full DataFrame for a timeframe."""
        return self.data.get(timeframe)

    def refresh_data(self, timeframe=None):
        """Refresh data for one or all timeframes."""
        if timeframe:
            count = CANDLE_COUNT.get(timeframe, 200)
            df = self.fetch_candles(timeframe, count)
            if df is not None:
                self.data[timeframe] = df
                self._calculate_indicators(timeframe)
                return True
            return False
        else:
            return self.fetch_all_timeframes()
