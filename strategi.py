"""
=============================================================================
STRATEGI - Advanced Trading Strategies
=============================================================================
1. Breakout + Pullback Strategy
2. QM (Quasimodo) Pattern Strategy
3. Supply & Demand Zone Strategy
4. Order Block Strategy (ICT/Smart Money)
5. Multi-Timeframe Confluence
6. RBR/DBD Micro Pattern (M1/M3)
=============================================================================
"""

import numpy as np
import pandas as pd
from datetime import datetime
import logging

from config import (
    BREAKOUT_CONFIG, QM_CONFIG, MTF_CONFIG,
    MICRO_PATTERN_CONFIG, RISK_CONFIG, SR_CONFIG
)

logger = logging.getLogger(__name__)


# ===================== SIGNAL CLASS =====================
class TradeSignal:
    """Represents a trade signal with all relevant information."""

    def __init__(self):
        self.direction = None       # 'buy' or 'sell'
        self.strategy = None        # 'breakout_pullback', 'qm_pattern', 'rbr_dbd'
        self.entry_price = 0.0
        self.stop_loss = 0.0
        self.take_profit = 0.0
        self.confidence = 0.0       # 0.0 - 1.0
        self.risk_reward = 0.0
        self.timeframe = None
        self.pattern_details = {}
        self.confluence_score = 0.0
        self.timestamp = datetime.utcnow()
        self.valid = False

    def to_dict(self):
        return {
            'direction': self.direction,
            'strategy': self.strategy,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'confidence': self.confidence,
            'risk_reward': self.risk_reward,
            'timeframe': self.timeframe,
            'pattern_details': self.pattern_details,
            'confluence_score': self.confluence_score,
            'timestamp': str(self.timestamp),
            'valid': self.valid,
        }

    def __repr__(self):
        return (
            f"Signal({self.direction} | {self.strategy} | "
            f"Entry:{self.entry_price:.2f} SL:{self.stop_loss:.2f} "
            f"TP:{self.take_profit:.2f} | RR:{self.risk_reward:.1f} | "
            f"Conf:{self.confidence:.2f})"
        )


# ===================== BREAKOUT + PULLBACK STRATEGY =====================
class BreakoutPullbackStrategy:
    """
    Breakout + Pullback to OB/SD Zone Strategy (M5):
    1. Identify strong SR levels
    2. Detect breakout (close above/below SR with strong body)
    3. Find nearest Order Block or Supply & Demand zone near broken SR
    4. Wait for pullback/retest to OB or SD zone (NOT just raw SR level)
    5. Enter on confirmation candle after pullback touches OB/SD zone
    6. SL below/above OB/SD zone, TP based on RR ratio

    Key improvement: Entry is refined by waiting for pullback to
    institutional zones (OB/SD) rather than plain SR level, giving
    higher probability entries with tighter stops.
    """

    def __init__(self, data_handler):
        self.data = data_handler
        self.config = BREAKOUT_CONFIG
        self.name = "breakout_pullback"

    def analyze(self, timeframe="M5"):
        """
        Analyze for Breakout + Pullback to OB/SD zone setup.

        Returns:
            TradeSignal or None
        """
        df = self.data.get_data(timeframe)
        if df is None or len(df) < self.config['lookback_period'] + 10:
            return None

        sr_levels = self.data.sr_levels
        if not sr_levels:
            sr_levels = self.data.calculate_sr_levels(timeframe)

        if not sr_levels:
            logger.debug("No SR levels found for breakout analysis")
            return None

        pip_value = self.data._get_pip_value()
        current_price = df['close'].iloc[-1]

        # Detect OB and SD zones for pullback targets
        ob_zones = self._detect_order_blocks_local(df, pip_value)
        sd_zones = self._detect_sd_zones_local(df, pip_value)

        # Check for recent breakout with pullback to OB/SD zone
        signal = self._detect_breakout_pullback(
            df, sr_levels, pip_value, current_price, ob_zones, sd_zones
        )

        if signal and signal.valid:
            # Add confluence score
            signal.confluence_score = self._calculate_confluence(
                signal, df, timeframe
            )
            signal.confidence = signal.confluence_score
            logger.info(f"Breakout+Pullback(OB/SD) signal: {signal}")

        return signal if signal and signal.valid else None

    def _detect_breakout_pullback(self, df, sr_levels, pip_value, current_price,
                                    ob_zones, sd_zones):
        """
        Detect breakout followed by pullback to nearest OB/SD zone.
        """
        lookback = self.config['lookback_period']
        breakout_threshold = self.config['breakout_threshold_pips'] * pip_value
        pullback_zone = self.config['pullback_zone_pips'] * pip_value
        max_pullback_candles = self.config['pullback_max_candles']

        signal = TradeSignal()
        signal.strategy = self.name

        for sr in sr_levels[:10]:  # Check top 10 strongest levels
            sr_price = sr['price']
            sr_type = sr['type']

            # --- BULLISH BREAKOUT (Break resistance, pullback to OB/SD zone) ---
            if sr_type == 'resistance':
                breakout_signal = self._check_bullish_breakout(
                    df, sr_price, pip_value, breakout_threshold,
                    pullback_zone, max_pullback_candles, current_price,
                    ob_zones, sd_zones
                )
                if breakout_signal:
                    return breakout_signal

            # --- BEARISH BREAKOUT (Break support, pullback to OB/SD zone) ---
            elif sr_type == 'support':
                breakout_signal = self._check_bearish_breakout(
                    df, sr_price, pip_value, breakout_threshold,
                    pullback_zone, max_pullback_candles, current_price,
                    ob_zones, sd_zones
                )
                if breakout_signal:
                    return breakout_signal

        return None

    def _check_bullish_breakout(self, df, sr_price, pip_value,
                                 breakout_threshold, pullback_zone,
                                 max_pullback_candles, current_price,
                                 ob_zones, sd_zones):
        """
        Check for bullish breakout + pullback to OB/SD zone setup.

        After breakout of resistance:
        1. Find nearest demand zone (OB bullish or SD demand) below/near broken SR
        2. Wait for price to pull back and retest that zone
        3. Enter on confirmation candle after retest
        """
        signal = TradeSignal()
        signal.strategy = self.name
        signal.direction = 'buy'

        # Look for breakout candle in recent history
        for i in range(-max_pullback_candles - 5, -max_pullback_candles):
            if i >= len(df) or abs(i) > len(df):
                continue

            candle = df.iloc[i]

            # Check if this candle broke resistance
            broke_above = (
                candle['close'] > sr_price + breakout_threshold and
                candle['open'] < sr_price and
                candle['body_ratio'] > self.config['body_ratio_min'] and
                candle['is_bullish']
            )

            if broke_above:
                # Find nearest OB/SD zone for pullback target (near/below SR)
                target_zone = self._find_nearest_zone_for_pullback(
                    sr_price, pip_value, 'buy', ob_zones, sd_zones
                )

                if target_zone is None:
                    # Fallback: no OB/SD found, skip this setup
                    logger.debug(
                        f"Bullish breakout at {sr_price:.2f} but no OB/SD zone found for pullback"
                    )
                    continue

                zone_high = target_zone['high']
                zone_low = target_zone['low']
                zone_buffer = 5 * pip_value

                # Check if price pulled back to the OB/SD zone
                pullback_to_zone = False
                confirmation = False

                for j in range(i + 1, min(i + max_pullback_candles + 1, -1)):
                    if abs(j) > len(df):
                        continue

                    pb_candle = df.iloc[j]

                    # Price entered or touched the OB/SD zone
                    if (pb_candle['low'] <= zone_high + zone_buffer and
                            pb_candle['low'] >= zone_low - zone_buffer):
                        pullback_to_zone = True

                    # After pullback to zone, check confirmation (bullish reaction)
                    if pullback_to_zone and j > i + 1:
                        if (pb_candle['is_bullish'] and
                                pb_candle['body_ratio'] > 0.5 and
                                pb_candle['close'] > zone_high):
                            confirmation = True
                            break

                if pullback_to_zone and confirmation:
                    # Valid setup - check if current price is in entry zone
                    if (current_price >= zone_high and
                            current_price <= zone_high + pullback_zone * 2):

                        signal.entry_price = current_price
                        signal.stop_loss = zone_low - (10 * pip_value)
                        signal.timeframe = "M5"

                        # Ensure SL within limits
                        sl_pips = (signal.entry_price - signal.stop_loss) / pip_value
                        if sl_pips < RISK_CONFIG['sl_min_pips']:
                            signal.stop_loss = signal.entry_price - (RISK_CONFIG['sl_min_pips'] * pip_value)
                        elif sl_pips > RISK_CONFIG['sl_max_pips']:
                            signal.stop_loss = signal.entry_price - (RISK_CONFIG['sl_max_pips'] * pip_value)

                        # Calculate TP based on RR
                        sl_distance = signal.entry_price - signal.stop_loss
                        signal.take_profit = signal.entry_price + (sl_distance * RISK_CONFIG['rr_minimum'])
                        signal.risk_reward = RISK_CONFIG['rr_minimum']

                        signal.pattern_details = {
                            'sr_level': sr_price,
                            'breakout_candle_index': i,
                            'pullback_found': True,
                            'pullback_zone_type': target_zone['zone_type'],
                            'zone_high': zone_high,
                            'zone_low': zone_low,
                            'pattern': 'bullish_breakout_pullback_ob_sd'
                        }
                        signal.valid = True
                        return signal

        return None

    def _check_bearish_breakout(self, df, sr_price, pip_value,
                                 breakout_threshold, pullback_zone,
                                 max_pullback_candles, current_price,
                                 ob_zones, sd_zones):
        """
        Check for bearish breakout + pullback to OB/SD zone setup.

        After breakout of support:
        1. Find nearest supply zone (OB bearish or SD supply) above/near broken SR
        2. Wait for price to pull back and retest that zone
        3. Enter on confirmation candle after retest
        """
        signal = TradeSignal()
        signal.strategy = self.name
        signal.direction = 'sell'

        for i in range(-max_pullback_candles - 5, -max_pullback_candles):
            if i >= len(df) or abs(i) > len(df):
                continue

            candle = df.iloc[i]

            # Check if this candle broke support
            broke_below = (
                candle['close'] < sr_price - breakout_threshold and
                candle['open'] > sr_price and
                candle['body_ratio'] > self.config['body_ratio_min'] and
                not candle['is_bullish']
            )

            if broke_below:
                # Find nearest OB/SD zone for pullback target (near/above SR)
                target_zone = self._find_nearest_zone_for_pullback(
                    sr_price, pip_value, 'sell', ob_zones, sd_zones
                )

                if target_zone is None:
                    # No OB/SD found, skip this setup
                    logger.debug(
                        f"Bearish breakout at {sr_price:.2f} but no OB/SD zone found for pullback"
                    )
                    continue

                zone_high = target_zone['high']
                zone_low = target_zone['low']
                zone_buffer = 5 * pip_value

                # Check if price pulled back to the OB/SD zone
                pullback_to_zone = False
                confirmation = False

                for j in range(i + 1, min(i + max_pullback_candles + 1, -1)):
                    if abs(j) > len(df):
                        continue

                    pb_candle = df.iloc[j]

                    # Price entered or touched the OB/SD zone (from below)
                    if (pb_candle['high'] >= zone_low - zone_buffer and
                            pb_candle['high'] <= zone_high + zone_buffer):
                        pullback_to_zone = True

                    # After pullback to zone, check confirmation (bearish reaction)
                    if pullback_to_zone and j > i + 1:
                        if (not pb_candle['is_bullish'] and
                                pb_candle['body_ratio'] > 0.5 and
                                pb_candle['close'] < zone_low):
                            confirmation = True
                            break

                if pullback_to_zone and confirmation:
                    # Valid setup - check if current price is in entry zone
                    if (current_price <= zone_low and
                            current_price >= zone_low - pullback_zone * 2):

                        signal.entry_price = current_price
                        signal.stop_loss = zone_high + (10 * pip_value)
                        signal.timeframe = "M5"

                        # Ensure SL within limits
                        sl_pips = (signal.stop_loss - signal.entry_price) / pip_value
                        if sl_pips < RISK_CONFIG['sl_min_pips']:
                            signal.stop_loss = signal.entry_price + (RISK_CONFIG['sl_min_pips'] * pip_value)
                        elif sl_pips > RISK_CONFIG['sl_max_pips']:
                            signal.stop_loss = signal.entry_price + (RISK_CONFIG['sl_max_pips'] * pip_value)

                        sl_distance = signal.stop_loss - signal.entry_price
                        signal.take_profit = signal.entry_price - (sl_distance * RISK_CONFIG['rr_minimum'])
                        signal.risk_reward = RISK_CONFIG['rr_minimum']

                        signal.pattern_details = {
                            'sr_level': sr_price,
                            'breakout_candle_index': i,
                            'pullback_found': True,
                            'pullback_zone_type': target_zone['zone_type'],
                            'zone_high': zone_high,
                            'zone_low': zone_low,
                            'pattern': 'bearish_breakout_pullback_ob_sd'
                        }
                        signal.valid = True
                        return signal

        return None

    def _find_nearest_zone_for_pullback(self, sr_price, pip_value, direction,
                                         ob_zones, sd_zones):
        """
        Find the nearest Order Block or Supply & Demand zone near the broken SR level.

        For BUY (bullish breakout): Look for demand zones (bullish OB / demand SD)
            near or just below the broken resistance level.
        For SELL (bearish breakout): Look for supply zones (bearish OB / supply SD)
            near or just above the broken support level.

        Args:
            sr_price: The broken SR price level
            pip_value: Value of one pip
            direction: 'buy' or 'sell'
            ob_zones: List of detected order blocks
            sd_zones: List of detected supply/demand zones

        Returns:
            dict with 'high', 'low', 'zone_type' or None
        """
        max_distance_pips = 50  # Max distance from SR to consider a zone relevant
        max_distance = max_distance_pips * pip_value
        candidates = []

        if direction == 'buy':
            # Look for demand zones (bullish OB or demand SD) near/below SR
            for ob in ob_zones:
                if ob['type'] == 'bullish_ob':
                    # Zone should be near or below the broken resistance
                    zone_mid = (ob['high'] + ob['low']) / 2
                    distance = sr_price - zone_mid
                    if -10 * pip_value <= distance <= max_distance:
                        candidates.append({
                            'high': ob['high'],
                            'low': ob['low'],
                            'zone_type': 'order_block',
                            'distance': abs(distance),
                            'strength': ob.get('impulse_strength', 0),
                        })

            for sd in sd_zones:
                if sd['type'] == 'demand':
                    zone_mid = (sd['high'] + sd['low']) / 2
                    distance = sr_price - zone_mid
                    if -10 * pip_value <= distance <= max_distance:
                        candidates.append({
                            'high': sd['high'],
                            'low': sd['low'],
                            'zone_type': 'supply_demand',
                            'distance': abs(distance),
                            'strength': sd.get('departure_strength', 0),
                        })

        elif direction == 'sell':
            # Look for supply zones (bearish OB or supply SD) near/above SR
            for ob in ob_zones:
                if ob['type'] == 'bearish_ob':
                    zone_mid = (ob['high'] + ob['low']) / 2
                    distance = zone_mid - sr_price
                    if -10 * pip_value <= distance <= max_distance:
                        candidates.append({
                            'high': ob['high'],
                            'low': ob['low'],
                            'zone_type': 'order_block',
                            'distance': abs(distance),
                            'strength': ob.get('impulse_strength', 0),
                        })

            for sd in sd_zones:
                if sd['type'] == 'supply':
                    zone_mid = (sd['high'] + sd['low']) / 2
                    distance = zone_mid - sr_price
                    if -10 * pip_value <= distance <= max_distance:
                        candidates.append({
                            'high': sd['high'],
                            'low': sd['low'],
                            'zone_type': 'supply_demand',
                            'distance': abs(distance),
                            'strength': sd.get('departure_strength', 0),
                        })

        if not candidates:
            return None

        # Sort: prioritize closest zone, then by strength
        candidates.sort(key=lambda z: (z['distance'], -z['strength']))
        return candidates[0]

    def _detect_order_blocks_local(self, df, pip_value):
        """
        Detect Order Blocks locally for breakout pullback analysis.
        Simplified detection of OB zones within the current M5 data.

        Returns:
            List of OB zone dicts with 'type', 'high', 'low', 'impulse_strength'
        """
        order_blocks = []
        min_impulse = 20 * pip_value
        lookback = min(len(df) - 5, 80)

        for i in range(5, lookback):
            # === BULLISH ORDER BLOCK ===
            # Last bearish candle before strong bullish impulse
            if not df['is_bullish'].iloc[i]:
                # Check next 2-4 candles for bullish displacement
                check_end = min(i + 5, len(df))
                total_move = 0
                bullish_count = 0

                for j in range(i + 1, check_end):
                    if df['is_bullish'].iloc[j]:
                        bullish_count += 1
                        total_move += df['body'].iloc[j]

                if bullish_count >= 2 and total_move >= min_impulse:
                    ob_high = df['high'].iloc[i]
                    ob_low = df['low'].iloc[i]

                    # Check if not mitigated (price hasn't closed below OB low)
                    mitigated = False
                    for k in range(i + 1, len(df) - 1):
                        if df['close'].iloc[k] < ob_low:
                            mitigated = True
                            break

                    if not mitigated:
                        order_blocks.append({
                            'type': 'bullish_ob',
                            'high': ob_high,
                            'low': ob_low,
                            'impulse_strength': total_move / pip_value,
                            'formed_index': i,
                        })

            # === BEARISH ORDER BLOCK ===
            # Last bullish candle before strong bearish impulse
            if df['is_bullish'].iloc[i]:
                check_end = min(i + 5, len(df))
                total_move = 0
                bearish_count = 0

                for j in range(i + 1, check_end):
                    if not df['is_bullish'].iloc[j]:
                        bearish_count += 1
                        total_move += df['body'].iloc[j]

                if bearish_count >= 2 and total_move >= min_impulse:
                    ob_high = df['high'].iloc[i]
                    ob_low = df['low'].iloc[i]

                    mitigated = False
                    for k in range(i + 1, len(df) - 1):
                        if df['close'].iloc[k] > ob_high:
                            mitigated = True
                            break

                    if not mitigated:
                        order_blocks.append({
                            'type': 'bearish_ob',
                            'high': ob_high,
                            'low': ob_low,
                            'impulse_strength': total_move / pip_value,
                            'formed_index': i,
                        })

        # Sort by recency
        order_blocks.sort(key=lambda ob: -ob['formed_index'])
        return order_blocks[:10]

    def _detect_sd_zones_local(self, df, pip_value):
        """
        Detect Supply & Demand zones locally for breakout pullback analysis.
        Simplified detection of SD zones within the current M5 data.

        Returns:
            List of SD zone dicts with 'type', 'high', 'low', 'departure_strength'
        """
        zones = []
        min_departure = 15 * pip_value
        lookback = min(len(df) - 5, 80)

        for i in range(5, lookback):
            # === DEMAND ZONE (strong bullish departure) ===
            if (df['is_bullish'].iloc[i] and
                    df['body'].iloc[i] > min_departure and
                    df['body_ratio'].iloc[i] > 0.6):

                # Find base before departure (2-5 small candles)
                base_start = None
                for length in range(2, 6):
                    start = i - length
                    if start < 0:
                        continue
                    segment = df.iloc[start:i]
                    avg_body_ratio = segment['body_ratio'].mean()
                    if avg_body_ratio < 0.55:
                        base_start = start
                        break

                if base_start is not None:
                    zone_high = df['high'].iloc[base_start:i].max()
                    zone_low = df['low'].iloc[base_start:i].min()
                    zone_width = zone_high - zone_low

                    if 3 * pip_value < zone_width < 50 * pip_value:
                        # Check freshness (not retested more than once)
                        tests = 0
                        in_zone = False
                        for k in range(i + 1, len(df)):
                            price_in = (df['low'].iloc[k] <= zone_high and
                                       df['high'].iloc[k] >= zone_low)
                            if price_in and not in_zone:
                                tests += 1
                                in_zone = True
                            elif not price_in:
                                in_zone = False

                        if tests <= 1:
                            zones.append({
                                'type': 'demand',
                                'high': zone_high,
                                'low': zone_low,
                                'departure_strength': df['body'].iloc[i] / pip_value,
                                'formed_index': i,
                                'fresh': tests == 0,
                            })

            # === SUPPLY ZONE (strong bearish departure) ===
            if (not df['is_bullish'].iloc[i] and
                    df['body'].iloc[i] > min_departure and
                    df['body_ratio'].iloc[i] > 0.6):

                base_start = None
                for length in range(2, 6):
                    start = i - length
                    if start < 0:
                        continue
                    segment = df.iloc[start:i]
                    avg_body_ratio = segment['body_ratio'].mean()
                    if avg_body_ratio < 0.55:
                        base_start = start
                        break

                if base_start is not None:
                    zone_high = df['high'].iloc[base_start:i].max()
                    zone_low = df['low'].iloc[base_start:i].min()
                    zone_width = zone_high - zone_low

                    if 3 * pip_value < zone_width < 50 * pip_value:
                        tests = 0
                        in_zone = False
                        for k in range(i + 1, len(df)):
                            price_in = (df['low'].iloc[k] <= zone_high and
                                       df['high'].iloc[k] >= zone_low)
                            if price_in and not in_zone:
                                tests += 1
                                in_zone = True
                            elif not price_in:
                                in_zone = False

                        if tests <= 1:
                            zones.append({
                                'type': 'supply',
                                'high': zone_high,
                                'low': zone_low,
                                'departure_strength': df['body'].iloc[i] / pip_value,
                                'formed_index': i,
                                'fresh': tests == 0,
                            })

        # Sort by recency
        zones.sort(key=lambda z: -z['formed_index'])
        return zones[:10]

    def _calculate_confluence(self, signal, df, timeframe):
        """Calculate confluence score for the signal (0-1)."""
        score = 0.0
        factors = 0

        # Factor 1: Volume confirmation
        if 'vol_ratio' in df.columns:
            recent_vol = df['vol_ratio'].iloc[-3:].mean()
            if recent_vol > self.config['volume_multiplier']:
                score += 1.0
            elif recent_vol > 1.0:
                score += 0.5
            factors += 1

        # Factor 2: Trend alignment (from M15)
        trend = self.data.get_trend_direction("M15")
        if trend:
            if signal.direction == 'buy' and trend['direction'] == 'bullish':
                score += 1.0
            elif signal.direction == 'sell' and trend['direction'] == 'bearish':
                score += 1.0
            elif trend['direction'] == 'neutral':
                score += 0.3
            factors += 1

        # Factor 3: EMA alignment
        if 'ema_fast' in df.columns and 'ema_slow' in df.columns:
            ema_f = df['ema_fast'].iloc[-1]
            ema_s = df['ema_slow'].iloc[-1]
            if signal.direction == 'buy' and ema_f > ema_s:
                score += 1.0
            elif signal.direction == 'sell' and ema_f < ema_s:
                score += 1.0
            factors += 1

        # Factor 4: RSI not overbought/oversold
        if 'rsi' in df.columns:
            rsi = df['rsi'].iloc[-1]
            if signal.direction == 'buy' and 30 < rsi < 70:
                score += 0.7
            elif signal.direction == 'sell' and 30 < rsi < 70:
                score += 0.7
            elif signal.direction == 'buy' and rsi < 30:
                score += 1.0  # Oversold for buy
            elif signal.direction == 'sell' and rsi > 70:
                score += 1.0  # Overbought for sell
            factors += 1

        # Factor 5: Body ratio of recent candles
        recent_body_ratio = df['body_ratio'].iloc[-3:].mean()
        if recent_body_ratio > 0.6:
            score += 0.8
        factors += 1

        return score / factors if factors > 0 else 0.5



# ===================== QM (QUASIMODO) PATTERN STRATEGY =====================
class QMPatternStrategy:
    """
    QM (Quasimodo) Pattern Strategy:

    Bullish QM:
    - Higher High (left shoulder)
    - Lower Low (head) - makes new low below previous swing low
    - Higher Low (right shoulder) - fails to make new low
    - Entry at neckline or right shoulder level
    - Pattern: HH -> LL -> HL

    Bearish QM:
    - Lower Low (left shoulder)
    - Higher High (head) - makes new high above previous swing high
    - Lower High (right shoulder) - fails to make new high
    - Entry at neckline or right shoulder level
    - Pattern: LL -> HH -> LH
    """

    def __init__(self, data_handler):
        self.data = data_handler
        self.config = QM_CONFIG
        self.name = "qm_pattern"

    def analyze(self, timeframe="M5"):
        """
        Analyze for QM pattern setup.

        Returns:
            TradeSignal or None
        """
        df = self.data.get_data(timeframe)
        if df is None or len(df) < self.config['swing_lookback'] + 10:
            return None

        # Get swing points
        swings = self.data.find_swing_points(timeframe)
        if len(swings) < 4:
            return None

        pip_value = self.data._get_pip_value()
        current_price = df['close'].iloc[-1]

        # Check for bullish QM
        bullish_signal = self._detect_bullish_qm(swings, pip_value, current_price, df)
        if bullish_signal and bullish_signal.valid:
            bullish_signal.confluence_score = self._calculate_qm_confluence(
                bullish_signal, df, timeframe
            )
            bullish_signal.confidence = bullish_signal.confluence_score
            logger.info(f"QM Bullish signal: {bullish_signal}")
            return bullish_signal

        # Check for bearish QM
        bearish_signal = self._detect_bearish_qm(swings, pip_value, current_price, df)
        if bearish_signal and bearish_signal.valid:
            bearish_signal.confluence_score = self._calculate_qm_confluence(
                bearish_signal, df, timeframe
            )
            bearish_signal.confidence = bearish_signal.confluence_score
            logger.info(f"QM Bearish signal: {bearish_signal}")
            return bearish_signal

        return None

    def _detect_bullish_qm(self, swings, pip_value, current_price, df):
        """
        Detect Bullish QM pattern.

        Pattern sequence:
        1. Swing High (left shoulder)
        2. Swing Low
        3. Higher High OR equal high
        4. Lower Low (head - makes new low)
        5. Price reverses up -> entry zone

        Simplified: Look for sequence where price makes lower low
        then fails to continue lower (higher low forms)
        """
        signal = TradeSignal()
        signal.strategy = self.name
        signal.direction = 'buy'

        min_height = self.config['min_pattern_height_pips'] * pip_value
        entry_zone = self.config['entry_zone_pips'] * pip_value

        # Get recent swing points (last 8-10)
        recent_swings = swings[-10:]
        swing_lows = [s for s in recent_swings if s['type'] == 'low']
        swing_highs = [s for s in recent_swings if s['type'] == 'high']

        if len(swing_lows) < 3 or len(swing_highs) < 2:
            return None

        # Pattern: We need at least 2 swing lows where:
        # - Second-to-last low is the LOWEST (head)
        # - Last low is HIGHER than the head (right shoulder / higher low)
        # This shows failed continuation to downside

        for i in range(len(swing_lows) - 2, 0, -1):
            if i + 1 >= len(swing_lows):
                continue

            prev_low = swing_lows[i - 1] if i > 0 else None
            head_low = swing_lows[i]       # The lowest point (head)
            right_low = swing_lows[i + 1]  # Higher low (right shoulder)

            if prev_low is None:
                continue

            # Conditions for Bullish QM:
            # 1. Head makes lower low than previous
            # 2. Right shoulder makes higher low than head
            # 3. Pattern height is sufficient
            is_head_lower = head_low['price'] < prev_low['price']
            is_right_higher = right_low['price'] > head_low['price']
            pattern_height = abs(prev_low['price'] - head_low['price'])

            if is_head_lower and is_right_higher and pattern_height >= min_height:
                # Find the neckline (high between head and right shoulder)
                neckline_highs = [
                    h for h in swing_highs
                    if head_low['index'] < h['index'] < right_low['index']
                ]

                if neckline_highs:
                    neckline = max(neckline_highs, key=lambda x: x['price'])['price']
                else:
                    # Use the high between the two lows
                    head_idx = head_low['index']
                    right_idx = right_low['index']
                    if head_idx < len(df) and right_idx < len(df):
                        neckline = df['high'].iloc[head_idx:right_idx].max()
                    else:
                        continue

                # Entry zone: near the right shoulder low or neckline break
                entry_level = right_low['price'] + entry_zone

                # Check if current price is in entry zone
                if (current_price >= right_low['price'] and
                        current_price <= entry_level + entry_zone):

                    signal.entry_price = current_price
                    signal.stop_loss = head_low['price'] - (5 * pip_value)

                    # Ensure SL is within limits
                    sl_pips = (signal.entry_price - signal.stop_loss) / pip_value
                    if sl_pips < RISK_CONFIG['sl_min_pips']:
                        signal.stop_loss = signal.entry_price - (RISK_CONFIG['sl_min_pips'] * pip_value)
                    elif sl_pips > RISK_CONFIG['sl_max_pips']:
                        signal.stop_loss = signal.entry_price - (RISK_CONFIG['sl_max_pips'] * pip_value)

                    # TP at neckline or beyond
                    sl_distance = signal.entry_price - signal.stop_loss
                    signal.take_profit = signal.entry_price + (sl_distance * RISK_CONFIG['rr_minimum'])

                    # If neckline is a better target
                    if neckline > signal.take_profit:
                        signal.take_profit = neckline
                        signal.risk_reward = (signal.take_profit - signal.entry_price) / sl_distance
                    else:
                        signal.risk_reward = RISK_CONFIG['rr_minimum']

                    signal.timeframe = "M5"
                    signal.pattern_details = {
                        'pattern': 'bullish_qm',
                        'head_price': head_low['price'],
                        'right_shoulder': right_low['price'],
                        'neckline': neckline,
                        'pattern_height_pips': pattern_height / pip_value,
                        'prev_low': prev_low['price'],
                    }
                    signal.valid = True
                    return signal

        return None

    def _detect_bearish_qm(self, swings, pip_value, current_price, df):
        """
        Detect Bearish QM pattern.

        Pattern: Price makes higher high then fails to continue higher
        (lower high forms) -> reversal signal
        """
        signal = TradeSignal()
        signal.strategy = self.name
        signal.direction = 'sell'

        min_height = self.config['min_pattern_height_pips'] * pip_value
        entry_zone = self.config['entry_zone_pips'] * pip_value

        recent_swings = swings[-10:]
        swing_lows = [s for s in recent_swings if s['type'] == 'low']
        swing_highs = [s for s in recent_swings if s['type'] == 'high']

        if len(swing_highs) < 3 or len(swing_lows) < 2:
            return None

        for i in range(len(swing_highs) - 2, 0, -1):
            if i + 1 >= len(swing_highs):
                continue

            prev_high = swing_highs[i - 1] if i > 0 else None
            head_high = swing_highs[i]       # The highest point (head)
            right_high = swing_highs[i + 1]  # Lower high (right shoulder)

            if prev_high is None:
                continue

            # Conditions for Bearish QM:
            # 1. Head makes higher high than previous
            # 2. Right shoulder makes lower high than head
            # 3. Pattern height is sufficient
            is_head_higher = head_high['price'] > prev_high['price']
            is_right_lower = right_high['price'] < head_high['price']
            pattern_height = abs(head_high['price'] - prev_high['price'])

            if is_head_higher and is_right_lower and pattern_height >= min_height:
                # Find the neckline (low between head and right shoulder)
                neckline_lows = [
                    l for l in swing_lows
                    if head_high['index'] < l['index'] < right_high['index']
                ]

                if neckline_lows:
                    neckline = min(neckline_lows, key=lambda x: x['price'])['price']
                else:
                    head_idx = head_high['index']
                    right_idx = right_high['index']
                    if head_idx < len(df) and right_idx < len(df):
                        neckline = df['low'].iloc[head_idx:right_idx].min()
                    else:
                        continue

                # Entry zone: near the right shoulder high
                entry_level = right_high['price'] - entry_zone

                if (current_price <= right_high['price'] and
                        current_price >= entry_level - entry_zone):

                    signal.entry_price = current_price
                    signal.stop_loss = head_high['price'] + (5 * pip_value)

                    # Ensure SL is within limits
                    sl_pips = (signal.stop_loss - signal.entry_price) / pip_value
                    if sl_pips < RISK_CONFIG['sl_min_pips']:
                        signal.stop_loss = signal.entry_price + (RISK_CONFIG['sl_min_pips'] * pip_value)
                    elif sl_pips > RISK_CONFIG['sl_max_pips']:
                        signal.stop_loss = signal.entry_price + (RISK_CONFIG['sl_max_pips'] * pip_value)

                    # TP
                    sl_distance = signal.stop_loss - signal.entry_price
                    signal.take_profit = signal.entry_price - (sl_distance * RISK_CONFIG['rr_minimum'])

                    if neckline < signal.take_profit:
                        signal.take_profit = neckline
                        signal.risk_reward = (signal.entry_price - signal.take_profit) / sl_distance
                    else:
                        signal.risk_reward = RISK_CONFIG['rr_minimum']

                    signal.timeframe = "M5"
                    signal.pattern_details = {
                        'pattern': 'bearish_qm',
                        'head_price': head_high['price'],
                        'right_shoulder': right_high['price'],
                        'neckline': neckline,
                        'pattern_height_pips': pattern_height / pip_value,
                        'prev_high': prev_high['price'],
                    }
                    signal.valid = True
                    return signal

        return None

    def _calculate_qm_confluence(self, signal, df, timeframe):
        """Calculate confluence score for QM pattern."""
        score = 0.0
        factors = 0

        # Factor 1: Pattern height (bigger = stronger)
        height_pips = signal.pattern_details.get('pattern_height_pips', 0)
        if height_pips > 50:
            score += 1.0
        elif height_pips > 30:
            score += 0.7
        else:
            score += 0.4
        factors += 1

        # Factor 2: Trend alignment
        trend = self.data.get_trend_direction("M15")
        if trend:
            if signal.direction == 'buy' and trend['direction'] == 'bullish':
                score += 1.0
            elif signal.direction == 'sell' and trend['direction'] == 'bearish':
                score += 1.0
            elif trend['direction'] == 'neutral':
                score += 0.5
            else:
                score += 0.2  # Counter-trend QM (still valid but less confident)
            factors += 1

        # Factor 3: Volume at pattern points
        if 'vol_ratio' in df.columns:
            recent_vol = df['vol_ratio'].iloc[-5:].mean()
            if recent_vol > 1.3:
                score += 1.0
            elif recent_vol > 1.0:
                score += 0.6
            else:
                score += 0.3
            factors += 1

        # Factor 4: RSI divergence check
        if 'rsi' in df.columns:
            rsi = df['rsi'].iloc[-1]
            if signal.direction == 'buy' and rsi < 40:
                score += 0.8  # RSI showing oversold for bullish QM
            elif signal.direction == 'sell' and rsi > 60:
                score += 0.8  # RSI showing overbought for bearish QM
            else:
                score += 0.4
            factors += 1

        # Factor 5: SR level proximity
        sr_levels = self.data.sr_levels
        if sr_levels:
            current = signal.entry_price
            nearest_sr = min(sr_levels, key=lambda x: abs(x['price'] - current))
            distance_pips = abs(nearest_sr['price'] - current) / self.data._get_pip_value()
            if distance_pips < 20:
                score += 0.9  # Near strong SR level
            elif distance_pips < 40:
                score += 0.5
            factors += 1

        return score / factors if factors > 0 else 0.5



# ===================== RBR/DBD MICRO PATTERN (M1/M3) =====================
class MicroPatternStrategy:
    """
    RBR (Rally-Base-Rally) and DBD (Drop-Base-Drop) patterns on M1/M3.
    Used for fine-tuning entries after higher timeframe signals.

    RBR: Strong bullish move -> consolidation (base) -> continuation up
    DBD: Strong bearish move -> consolidation (base) -> continuation down
    """

    def __init__(self, data_handler):
        self.data = data_handler
        self.config = MICRO_PATTERN_CONFIG
        self.name = "rbr_dbd"

    def analyze(self, timeframe="M1", bias=None):
        """
        Analyze for RBR/DBD micro patterns.

        Args:
            timeframe: M1 or M3
            bias: 'buy' or 'sell' - only look for patterns matching bias

        Returns:
            TradeSignal or None
        """
        df = self.data.get_data(timeframe)
        if df is None or len(df) < self.config['pattern_lookback'] + 10:
            return None

        pip_value = self.data._get_pip_value()
        current_price = df['close'].iloc[-1]

        if bias is None or bias == 'buy':
            rbr_signal = self._detect_rbr(df, pip_value, current_price)
            if rbr_signal and rbr_signal.valid:
                return rbr_signal

        if bias is None or bias == 'sell':
            dbd_signal = self._detect_dbd(df, pip_value, current_price)
            if dbd_signal and dbd_signal.valid:
                return dbd_signal

        return None

    def _detect_rbr(self, df, pip_value, current_price):
        """
        Detect Rally-Base-Rally pattern.

        1. Rally: Strong bullish move (multiple bullish candles)
        2. Base: Small range consolidation (2-5 candles)
        3. Rally: Continuation bullish move
        """
        signal = TradeSignal()
        signal.strategy = self.name
        signal.direction = 'buy'

        lookback = self.config['pattern_lookback']
        base_max = self.config['base_max_candles']
        base_range = self.config['base_max_range_pips'] * pip_value
        rally_min = self.config['rally_min_pips'] * pip_value

        # Look for pattern in recent candles
        for start in range(len(df) - lookback, len(df) - base_max - 4):
            if start < 0:
                continue

            # Phase 1: First Rally (at least 3 bullish candles)
            rally1_end = None
            rally1_start_price = df['low'].iloc[start]
            for r in range(start, min(start + 8, len(df))):
                if df['close'].iloc[r] - rally1_start_price >= rally_min:
                    rally1_end = r
                    break

            if rally1_end is None:
                continue

            # Phase 2: Base (consolidation)
            base_start = rally1_end + 1
            base_end = None

            for b in range(base_start, min(base_start + base_max + 1, len(df))):
                segment = df.iloc[base_start:b + 1]
                if len(segment) < 2:
                    continue

                seg_range = segment['high'].max() - segment['low'].min()
                if seg_range <= base_range:
                    base_end = b
                else:
                    break

            if base_end is None or base_end - base_start < 1:
                continue

            # Phase 3: Second Rally (continuation)
            rally2_start = base_end + 1
            if rally2_start >= len(df) - 1:
                continue

            base_high = df['high'].iloc[base_start:base_end + 1].max()
            base_low = df['low'].iloc[base_start:base_end + 1].min()

            # Check if current price broke above base
            if current_price > base_high:
                signal.entry_price = current_price
                signal.stop_loss = base_low - (5 * pip_value)
                signal.timeframe = "M1"

                sl_distance = signal.entry_price - signal.stop_loss
                signal.take_profit = signal.entry_price + (sl_distance * RISK_CONFIG['rr_minimum'])
                signal.risk_reward = RISK_CONFIG['rr_minimum']

                signal.pattern_details = {
                    'pattern': 'rbr',
                    'base_high': base_high,
                    'base_low': base_low,
                    'rally1_distance_pips': (df['close'].iloc[rally1_end] - rally1_start_price) / pip_value,
                }
                signal.confidence = 0.6
                signal.valid = True
                return signal

        return None

    def _detect_dbd(self, df, pip_value, current_price):
        """
        Detect Drop-Base-Drop pattern.

        1. Drop: Strong bearish move
        2. Base: Small range consolidation
        3. Drop: Continuation bearish move
        """
        signal = TradeSignal()
        signal.strategy = self.name
        signal.direction = 'sell'

        lookback = self.config['pattern_lookback']
        base_max = self.config['base_max_candles']
        base_range = self.config['base_max_range_pips'] * pip_value
        drop_min = self.config['rally_min_pips'] * pip_value

        for start in range(len(df) - lookback, len(df) - base_max - 4):
            if start < 0:
                continue

            # Phase 1: First Drop
            drop1_end = None
            drop1_start_price = df['high'].iloc[start]
            for r in range(start, min(start + 8, len(df))):
                if drop1_start_price - df['close'].iloc[r] >= drop_min:
                    drop1_end = r
                    break

            if drop1_end is None:
                continue

            # Phase 2: Base
            base_start = drop1_end + 1
            base_end = None

            for b in range(base_start, min(base_start + base_max + 1, len(df))):
                segment = df.iloc[base_start:b + 1]
                if len(segment) < 2:
                    continue

                seg_range = segment['high'].max() - segment['low'].min()
                if seg_range <= base_range:
                    base_end = b
                else:
                    break

            if base_end is None or base_end - base_start < 1:
                continue

            # Phase 3: Second Drop
            rally2_start = base_end + 1
            if rally2_start >= len(df) - 1:
                continue

            base_high = df['high'].iloc[base_start:base_end + 1].max()
            base_low = df['low'].iloc[base_start:base_end + 1].min()

            # Check if current price broke below base
            if current_price < base_low:
                signal.entry_price = current_price
                signal.stop_loss = base_high + (5 * pip_value)
                signal.timeframe = "M1"

                sl_distance = signal.stop_loss - signal.entry_price
                signal.take_profit = signal.entry_price - (sl_distance * RISK_CONFIG['rr_minimum'])
                signal.risk_reward = RISK_CONFIG['rr_minimum']

                signal.pattern_details = {
                    'pattern': 'dbd',
                    'base_high': base_high,
                    'base_low': base_low,
                    'drop1_distance_pips': (drop1_start_price - df['close'].iloc[drop1_end]) / pip_value,
                }
                signal.confidence = 0.6
                signal.valid = True
                return signal

        return None


# ===================== SUPPLY & DEMAND ZONE STRATEGY =====================
class SupplyDemandStrategy:
    """
    Supply & Demand Zone Strategy:

    Supply Zone (Sell):
    - Area where strong selling occurred (big bearish candle after consolidation)
    - Price rallied UP into zone then dropped sharply
    - Fresh zone = not yet retested
    - Entry when price returns to untested supply zone

    Demand Zone (Buy):
    - Area where strong buying occurred (big bullish candle after consolidation)
    - Price dropped DOWN into zone then rallied sharply
    - Fresh zone = not yet retested
    - Entry when price returns to untested demand zone

    Zone Quality:
    - Departure strength (how fast price left the zone)
    - Time spent in zone (less = stronger)
    - Number of times tested (fresh = best, 1 retest ok, 2+ = weak)
    """

    def __init__(self, data_handler):
        self.data = data_handler
        self.name = "supply_demand"
        self.zones = []  # List of active SD zones

    def analyze(self, timeframe="M5"):
        """
        Analyze for Supply & Demand zone entries.

        Returns:
            TradeSignal or None
        """
        df = self.data.get_data(timeframe)
        if df is None or len(df) < 50:
            return None

        pip_value = self.data._get_pip_value()
        current_price = df['close'].iloc[-1]

        # Detect fresh zones
        self.zones = self._detect_zones(df, pip_value)

        if not self.zones:
            return None

        # Check if price is entering any fresh zone
        signal = self._check_zone_entry(df, current_price, pip_value)

        if signal and signal.valid:
            signal.confluence_score = self._calculate_sd_confluence(signal, df, timeframe)
            signal.confidence = signal.confluence_score
            logger.info(f"Supply/Demand signal: {signal}")

        return signal if signal and signal.valid else None

    def _detect_zones(self, df, pip_value):
        """
        Detect Supply and Demand zones.

        A zone is formed when:
        1. Base candles (small body, consolidation) followed by
        2. Explosive move away (big body candle = departure)
        """
        zones = []
        min_departure_pips = 20 * pip_value  # Minimum departure strength

        for i in range(5, len(df) - 3):
            # Look for explosive bullish departure (DEMAND zone below)
            if (df['is_bullish'].iloc[i] and
                    df['body'].iloc[i] > min_departure_pips and
                    df['body_ratio'].iloc[i] > 0.65):

                # Check if there was a base before the departure
                base_start, base_end = self._find_base(df, i, direction='up')
                if base_start is not None:
                    zone_high = df['high'].iloc[base_start:base_end + 1].max()
                    zone_low = df['low'].iloc[base_start:base_end + 1].min()
                    zone_width = zone_high - zone_low

                    if zone_width > 3 * pip_value and zone_width < 50 * pip_value:
                        # Check if zone is still fresh (not retested)
                        tests = self._count_zone_tests(df, zone_low, zone_high, i + 1)

                        if tests <= 1:  # Fresh or tested once
                            zones.append({
                                'type': 'demand',
                                'high': zone_high,
                                'low': zone_low,
                                'mid': (zone_high + zone_low) / 2,
                                'width_pips': zone_width / pip_value,
                                'departure_strength': df['body'].iloc[i] / pip_value,
                                'base_candles': base_end - base_start + 1,
                                'formed_index': i,
                                'tests': tests,
                                'fresh': tests == 0,
                            })

            # Look for explosive bearish departure (SUPPLY zone above)
            if (not df['is_bullish'].iloc[i] and
                    df['body'].iloc[i] > min_departure_pips and
                    df['body_ratio'].iloc[i] > 0.65):

                base_start, base_end = self._find_base(df, i, direction='down')
                if base_start is not None:
                    zone_high = df['high'].iloc[base_start:base_end + 1].max()
                    zone_low = df['low'].iloc[base_start:base_end + 1].min()
                    zone_width = zone_high - zone_low

                    if zone_width > 3 * pip_value and zone_width < 50 * pip_value:
                        tests = self._count_zone_tests(df, zone_low, zone_high, i + 1)

                        if tests <= 1:
                            zones.append({
                                'type': 'supply',
                                'high': zone_high,
                                'low': zone_low,
                                'mid': (zone_high + zone_low) / 2,
                                'width_pips': zone_width / pip_value,
                                'departure_strength': df['body'].iloc[i] / pip_value,
                                'base_candles': base_end - base_start + 1,
                                'formed_index': i,
                                'tests': tests,
                                'fresh': tests == 0,
                            })

        # Sort by recency (most recent first) and freshness
        zones.sort(key=lambda z: (-int(z['fresh']), -z['formed_index']))
        return zones[:10]  # Keep top 10 zones

    def _find_base(self, df, departure_idx, direction='up'):
        """
        Find the base (consolidation) before a departure candle.
        Base = 2-5 candles with small bodies before the explosive move.
        """
        max_base_candles = 5
        min_base_candles = 2

        # Look backwards from the departure candle
        for length in range(min_base_candles, max_base_candles + 1):
            start = departure_idx - length
            if start < 0:
                continue

            segment = df.iloc[start:departure_idx]

            # Check if candles have small bodies (consolidation)
            avg_body_ratio = segment['body_ratio'].mean()
            max_range = segment['range'].max()
            avg_range = segment['range'].mean()

            # Base criteria: small body ratio, low volatility
            if avg_body_ratio < 0.55 and max_range < avg_range * 2.5:
                return start, departure_idx - 1

        return None, None

    def _count_zone_tests(self, df, zone_low, zone_high, start_idx):
        """Count how many times price has returned to a zone after formation."""
        tests = 0
        in_zone = False

        for i in range(start_idx, len(df)):
            price_in_zone = df['low'].iloc[i] <= zone_high and df['high'].iloc[i] >= zone_low

            if price_in_zone and not in_zone:
                tests += 1
                in_zone = True
            elif not price_in_zone:
                in_zone = False

        return tests

    def _check_zone_entry(self, df, current_price, pip_value):
        """Check if current price is entering a fresh zone."""
        entry_buffer = 5 * pip_value  # Enter slightly before zone edge

        for zone in self.zones:
            signal = TradeSignal()
            signal.strategy = self.name

            if zone['type'] == 'demand':
                # Price approaching demand zone from above
                if (current_price <= zone['high'] + entry_buffer and
                        current_price >= zone['low'] - entry_buffer):

                    signal.direction = 'buy'
                    signal.entry_price = current_price
                    signal.stop_loss = zone['low'] - (10 * pip_value)
                    signal.timeframe = "M5"

                    # Ensure SL within limits
                    sl_pips = (signal.entry_price - signal.stop_loss) / pip_value
                    if sl_pips < RISK_CONFIG['sl_min_pips']:
                        signal.stop_loss = signal.entry_price - (RISK_CONFIG['sl_min_pips'] * pip_value)
                    elif sl_pips > RISK_CONFIG['sl_max_pips']:
                        signal.stop_loss = signal.entry_price - (RISK_CONFIG['sl_max_pips'] * pip_value)

                    sl_distance = signal.entry_price - signal.stop_loss
                    signal.take_profit = signal.entry_price + (sl_distance * RISK_CONFIG['rr_minimum'])
                    signal.risk_reward = RISK_CONFIG['rr_minimum']

                    signal.pattern_details = {
                        'pattern': 'demand_zone_entry',
                        'zone_high': zone['high'],
                        'zone_low': zone['low'],
                        'departure_strength': zone['departure_strength'],
                        'fresh': zone['fresh'],
                        'tests': zone['tests'],
                    }
                    signal.valid = True
                    return signal

            elif zone['type'] == 'supply':
                # Price approaching supply zone from below
                if (current_price >= zone['low'] - entry_buffer and
                        current_price <= zone['high'] + entry_buffer):

                    signal.direction = 'sell'
                    signal.entry_price = current_price
                    signal.stop_loss = zone['high'] + (10 * pip_value)
                    signal.timeframe = "M5"

                    sl_pips = (signal.stop_loss - signal.entry_price) / pip_value
                    if sl_pips < RISK_CONFIG['sl_min_pips']:
                        signal.stop_loss = signal.entry_price + (RISK_CONFIG['sl_min_pips'] * pip_value)
                    elif sl_pips > RISK_CONFIG['sl_max_pips']:
                        signal.stop_loss = signal.entry_price + (RISK_CONFIG['sl_max_pips'] * pip_value)

                    sl_distance = signal.stop_loss - signal.entry_price
                    signal.take_profit = signal.entry_price - (sl_distance * RISK_CONFIG['rr_minimum'])
                    signal.risk_reward = RISK_CONFIG['rr_minimum']

                    signal.pattern_details = {
                        'pattern': 'supply_zone_entry',
                        'zone_high': zone['high'],
                        'zone_low': zone['low'],
                        'departure_strength': zone['departure_strength'],
                        'fresh': zone['fresh'],
                        'tests': zone['tests'],
                    }
                    signal.valid = True
                    return signal

        return None

    def _calculate_sd_confluence(self, signal, df, timeframe):
        """Calculate confluence score for Supply/Demand signal."""
        score = 0.0
        factors = 0

        # Factor 1: Zone freshness (fresh = best)
        if signal.pattern_details.get('fresh'):
            score += 1.0
        else:
            score += 0.5
        factors += 1

        # Factor 2: Departure strength
        dep_strength = signal.pattern_details.get('departure_strength', 0)
        if dep_strength > 40:
            score += 1.0
        elif dep_strength > 25:
            score += 0.7
        else:
            score += 0.4
        factors += 1

        # Factor 3: Trend alignment
        trend = self.data.get_trend_direction("M15")
        if trend:
            if signal.direction == 'buy' and trend['direction'] == 'bullish':
                score += 1.0
            elif signal.direction == 'sell' and trend['direction'] == 'bearish':
                score += 1.0
            elif trend['direction'] == 'neutral':
                score += 0.5
            else:
                score += 0.2
            factors += 1

        # Factor 4: Volume confirmation
        if 'vol_ratio' in df.columns:
            recent_vol = df['vol_ratio'].iloc[-3:].mean()
            if recent_vol > 1.2:
                score += 0.8
            else:
                score += 0.4
            factors += 1

        # Factor 5: RSI at zone
        if 'rsi' in df.columns:
            rsi = df['rsi'].iloc[-1]
            if signal.direction == 'buy' and rsi < 40:
                score += 0.9
            elif signal.direction == 'sell' and rsi > 60:
                score += 0.9
            else:
                score += 0.4
            factors += 1

        return score / factors if factors > 0 else 0.5


# ===================== ORDER BLOCK STRATEGY =====================
class OrderBlockStrategy:
    """
    Order Block Strategy (Institutional Trading Concept):

    Bullish Order Block:
    - Last bearish candle before a strong bullish impulse move
    - Represents institutional buying (smart money accumulation)
    - Entry when price returns to the order block zone

    Bearish Order Block:
    - Last bullish candle before a strong bearish impulse move
    - Represents institutional selling (smart money distribution)
    - Entry when price returns to the order block zone

    Criteria:
    - Impulse move must break structure (new high/low)
    - Order block candle must be followed by displacement
    - Displacement = 2-3 candles with strong momentum away
    - Order block zone = high to low of the OB candle
    """

    def __init__(self, data_handler):
        self.data = data_handler
        self.name = "order_block"
        self.order_blocks = []

    def analyze(self, timeframe="M5"):
        """
        Analyze for Order Block entries.

        Returns:
            TradeSignal or None
        """
        df = self.data.get_data(timeframe)
        if df is None or len(df) < 50:
            return None

        pip_value = self.data._get_pip_value()
        current_price = df['close'].iloc[-1]

        # Detect order blocks
        self.order_blocks = self._detect_order_blocks(df, pip_value)

        if not self.order_blocks:
            return None

        # Check if price is entering any unmitigated order block
        signal = self._check_ob_entry(df, current_price, pip_value)

        if signal and signal.valid:
            signal.confluence_score = self._calculate_ob_confluence(signal, df, timeframe)
            signal.confidence = signal.confluence_score
            logger.info(f"Order Block signal: {signal}")

        return signal if signal and signal.valid else None

    def _detect_order_blocks(self, df, pip_value):
        """
        Detect Order Blocks.

        Bullish OB: Last bearish candle before bullish impulse that breaks structure
        Bearish OB: Last bullish candle before bearish impulse that breaks structure
        """
        order_blocks = []
        min_impulse_pips = 25 * pip_value
        lookback = min(len(df) - 10, 100)  # Look back up to 100 candles

        for i in range(10, lookback):
            # === BULLISH ORDER BLOCK ===
            # Find bearish candle followed by strong bullish displacement
            if not df['is_bullish'].iloc[i]:
                # Check for bullish displacement (next 2-4 candles)
                displacement = self._check_displacement(df, i, 'bullish', min_impulse_pips)

                if displacement:
                    # This bearish candle is a Bullish Order Block
                    ob_high = df['high'].iloc[i]
                    ob_low = df['low'].iloc[i]

                    # Check if OB is unmitigated (price hasn't fully returned)
                    mitigated = self._is_mitigated(df, ob_low, ob_high, i + 1, 'bullish')

                    if not mitigated:
                        order_blocks.append({
                            'type': 'bullish_ob',
                            'high': ob_high,
                            'low': ob_low,
                            'mid': (ob_high + ob_low) / 2,
                            'width_pips': (ob_high - ob_low) / pip_value,
                            'impulse_strength': displacement['strength'],
                            'broke_structure': displacement['broke_structure'],
                            'formed_index': i,
                            'formed_time': df.index[i],
                            'mitigated': False,
                        })

            # === BEARISH ORDER BLOCK ===
            # Find bullish candle followed by strong bearish displacement
            if df['is_bullish'].iloc[i]:
                displacement = self._check_displacement(df, i, 'bearish', min_impulse_pips)

                if displacement:
                    ob_high = df['high'].iloc[i]
                    ob_low = df['low'].iloc[i]

                    mitigated = self._is_mitigated(df, ob_low, ob_high, i + 1, 'bearish')

                    if not mitigated:
                        order_blocks.append({
                            'type': 'bearish_ob',
                            'high': ob_high,
                            'low': ob_low,
                            'mid': (ob_high + ob_low) / 2,
                            'width_pips': (ob_high - ob_low) / pip_value,
                            'impulse_strength': displacement['strength'],
                            'broke_structure': displacement['broke_structure'],
                            'formed_index': i,
                            'formed_time': df.index[i],
                            'mitigated': False,
                        })

        # Sort by recency
        order_blocks.sort(key=lambda ob: -ob['formed_index'])
        return order_blocks[:8]  # Keep top 8

    def _check_displacement(self, df, ob_index, direction, min_impulse):
        """
        Check if there's a strong displacement after the OB candle.
        Displacement = 2-4 candles with strong momentum.
        """
        check_range = min(ob_index + 5, len(df))

        if direction == 'bullish':
            # Check next 2-4 candles for strong upward move
            total_move = 0
            bullish_count = 0

            for j in range(ob_index + 1, check_range):
                if df['is_bullish'].iloc[j]:
                    bullish_count += 1
                    total_move += df['body'].iloc[j]

            if bullish_count >= 2 and total_move >= min_impulse:
                # Check if it broke recent structure (swing high)
                recent_high = df['high'].iloc[max(0, ob_index - 20):ob_index].max()
                impulse_high = df['high'].iloc[ob_index + 1:check_range].max()
                broke = impulse_high > recent_high

                return {
                    'strength': total_move / self.data._get_pip_value(),
                    'candles': bullish_count,
                    'broke_structure': broke,
                }

        elif direction == 'bearish':
            total_move = 0
            bearish_count = 0

            for j in range(ob_index + 1, check_range):
                if not df['is_bullish'].iloc[j]:
                    bearish_count += 1
                    total_move += df['body'].iloc[j]

            if bearish_count >= 2 and total_move >= min_impulse:
                recent_low = df['low'].iloc[max(0, ob_index - 20):ob_index].min()
                impulse_low = df['low'].iloc[ob_index + 1:check_range].min()
                broke = impulse_low < recent_low

                return {
                    'strength': total_move / self.data._get_pip_value(),
                    'candles': bearish_count,
                    'broke_structure': broke,
                }

        return None

    def _is_mitigated(self, df, ob_low, ob_high, start_idx, ob_type):
        """
        Check if an order block has been mitigated.
        Mitigated = price has fully traded through the OB zone.
        """
        for i in range(start_idx, len(df) - 1):  # Exclude current candle
            if ob_type == 'bullish':
                # Bullish OB mitigated if price closes below OB low
                if df['close'].iloc[i] < ob_low:
                    return True
            elif ob_type == 'bearish':
                # Bearish OB mitigated if price closes above OB high
                if df['close'].iloc[i] > ob_high:
                    return True

        return False

    def _check_ob_entry(self, df, current_price, pip_value):
        """Check if current price is entering an unmitigated order block."""
        entry_buffer = 3 * pip_value

        for ob in self.order_blocks:
            signal = TradeSignal()
            signal.strategy = self.name

            if ob['type'] == 'bullish_ob':
                # Price returning to bullish OB = buy opportunity
                if (current_price <= ob['high'] + entry_buffer and
                        current_price >= ob['low'] - entry_buffer):

                    signal.direction = 'buy'
                    signal.entry_price = current_price
                    signal.stop_loss = ob['low'] - (10 * pip_value)
                    signal.timeframe = "M5"

                    sl_pips = (signal.entry_price - signal.stop_loss) / pip_value
                    if sl_pips < RISK_CONFIG['sl_min_pips']:
                        signal.stop_loss = signal.entry_price - (RISK_CONFIG['sl_min_pips'] * pip_value)
                    elif sl_pips > RISK_CONFIG['sl_max_pips']:
                        signal.stop_loss = signal.entry_price - (RISK_CONFIG['sl_max_pips'] * pip_value)

                    sl_distance = signal.entry_price - signal.stop_loss
                    signal.take_profit = signal.entry_price + (sl_distance * RISK_CONFIG['rr_minimum'])
                    signal.risk_reward = RISK_CONFIG['rr_minimum']

                    signal.pattern_details = {
                        'pattern': 'bullish_order_block',
                        'ob_high': ob['high'],
                        'ob_low': ob['low'],
                        'impulse_strength': ob['impulse_strength'],
                        'broke_structure': ob['broke_structure'],
                        'width_pips': ob['width_pips'],
                    }
                    signal.valid = True
                    return signal

            elif ob['type'] == 'bearish_ob':
                # Price returning to bearish OB = sell opportunity
                if (current_price >= ob['low'] - entry_buffer and
                        current_price <= ob['high'] + entry_buffer):

                    signal.direction = 'sell'
                    signal.entry_price = current_price
                    signal.stop_loss = ob['high'] + (10 * pip_value)
                    signal.timeframe = "M5"

                    sl_pips = (signal.stop_loss - signal.entry_price) / pip_value
                    if sl_pips < RISK_CONFIG['sl_min_pips']:
                        signal.stop_loss = signal.entry_price + (RISK_CONFIG['sl_min_pips'] * pip_value)
                    elif sl_pips > RISK_CONFIG['sl_max_pips']:
                        signal.stop_loss = signal.entry_price + (RISK_CONFIG['sl_max_pips'] * pip_value)

                    sl_distance = signal.stop_loss - signal.entry_price
                    signal.take_profit = signal.entry_price - (sl_distance * RISK_CONFIG['rr_minimum'])
                    signal.risk_reward = RISK_CONFIG['rr_minimum']

                    signal.pattern_details = {
                        'pattern': 'bearish_order_block',
                        'ob_high': ob['high'],
                        'ob_low': ob['low'],
                        'impulse_strength': ob['impulse_strength'],
                        'broke_structure': ob['broke_structure'],
                        'width_pips': ob['width_pips'],
                    }
                    signal.valid = True
                    return signal

        return None

    def _calculate_ob_confluence(self, signal, df, timeframe):
        """Calculate confluence score for Order Block signal."""
        score = 0.0
        factors = 0

        # Factor 1: Structure break (key for OB validity)
        if signal.pattern_details.get('broke_structure'):
            score += 1.0
        else:
            score += 0.4
        factors += 1

        # Factor 2: Impulse strength
        impulse = signal.pattern_details.get('impulse_strength', 0)
        if impulse > 50:
            score += 1.0
        elif impulse > 30:
            score += 0.7
        else:
            score += 0.4
        factors += 1

        # Factor 3: Trend alignment
        trend = self.data.get_trend_direction("M15")
        if trend:
            if signal.direction == 'buy' and trend['direction'] == 'bullish':
                score += 1.0
            elif signal.direction == 'sell' and trend['direction'] == 'bearish':
                score += 1.0
            elif trend['direction'] == 'neutral':
                score += 0.5
            else:
                score += 0.2
            factors += 1

        # Factor 4: OB width (smaller = more precise)
        width = signal.pattern_details.get('width_pips', 30)
        if width < 15:
            score += 0.9
        elif width < 30:
            score += 0.7
        else:
            score += 0.4
        factors += 1

        # Factor 5: Volume at OB
        if 'vol_ratio' in df.columns:
            recent_vol = df['vol_ratio'].iloc[-3:].mean()
            if recent_vol > 1.3:
                score += 0.9
            elif recent_vol > 1.0:
                score += 0.6
            else:
                score += 0.3
            factors += 1

        return score / factors if factors > 0 else 0.5


# ===================== MULTI-TIMEFRAME CONFLUENCE =====================
class MultiTimeframeAnalyzer:
    """
    Combines signals from multiple timeframes:
    - M15: Trend direction
    - M5: Main signals (Breakout+Pullback, QM)
    - M1/M3: Fine-tuning entry (RBR/DBD)

    Only takes trades when multiple timeframes align.
    """

    def __init__(self, data_handler):
        self.data = data_handler
        self.breakout_strategy = BreakoutPullbackStrategy(data_handler)
        self.qm_strategy = QMPatternStrategy(data_handler)
        self.micro_strategy = MicroPatternStrategy(data_handler)
        self.sd_strategy = SupplyDemandStrategy(data_handler)
        self.ob_strategy = OrderBlockStrategy(data_handler)

    def analyze(self):
        """
        Full multi-timeframe analysis.
        STRICT MODE: Only returns signals that are properly aligned with trend.
        Maximum 1 signal returned (the best one).

        Returns:
            list of TradeSignal (sorted by confidence)
        """
        signals = []

        # Step 1: Get M15 trend
        trend = self.data.get_trend_direction("M15")
        if not trend:
            logger.warning("Could not determine M15 trend")
            return signals

        trend_direction = trend['direction']
        trend_strength = trend['strength']

        logger.info(f"M15 Trend: {trend_direction} (strength: {trend_strength:.2f})")

        # Step 2: STRICT - Only trade with clear trend direction
        if trend_direction == 'neutral':
            logger.info(f"No clear trend direction (neutral) - skipping")
            return signals

        # If trend has a direction but strength is very low, still allow but log it
        if trend_strength < MTF_CONFIG['trend_strength_min']:
            logger.info(f"Weak trend ({trend_direction}, strength={trend_strength:.2f}) - proceeding with caution")

        # Step 3: Get M5 signals - ONLY aligned with trend
        breakout_signal = self.breakout_strategy.analyze("M5")
        qm_signal = self.qm_strategy.analyze("M5")
        sd_signal = self.sd_strategy.analyze("M5")
        ob_signal = self.ob_strategy.analyze("M5")

        # Step 4: STRICT FILTER - Only add signals that align with M15 trend
        # No counter-trend trades allowed
        if breakout_signal and self._is_aligned(breakout_signal, trend_direction):
            # Require micro confirmation for extra safety
            micro_signal = self.micro_strategy.analyze("M1", bias=breakout_signal.direction)
            if micro_signal:
                breakout_signal.confidence *= 1.15
                breakout_signal.pattern_details['micro_confirmation'] = True
            signals.append(breakout_signal)

        if qm_signal and self._is_aligned(qm_signal, trend_direction):
            micro_signal = self.micro_strategy.analyze("M1", bias=qm_signal.direction)
            if micro_signal:
                qm_signal.confidence *= 1.15
                qm_signal.pattern_details['micro_confirmation'] = True
            signals.append(qm_signal)

        if sd_signal and self._is_aligned(sd_signal, trend_direction):
            # SD: Only accept fresh zones
            if sd_signal.pattern_details.get('fresh', False):
                micro_signal = self.micro_strategy.analyze("M1", bias=sd_signal.direction)
                if micro_signal:
                    sd_signal.confidence *= 1.15
                    sd_signal.pattern_details['micro_confirmation'] = True
                signals.append(sd_signal)
            else:
                logger.debug("SD signal rejected: zone not fresh")

        if ob_signal and self._is_aligned(ob_signal, trend_direction):
            # OB: Only accept if structure was broken
            if ob_signal.pattern_details.get('broke_structure', False):
                micro_signal = self.micro_strategy.analyze("M1", bias=ob_signal.direction)
                if micro_signal:
                    ob_signal.confidence *= 1.15
                    ob_signal.pattern_details['micro_confirmation'] = True
                signals.append(ob_signal)
            else:
                logger.debug("OB signal rejected: no structure break")

        # Step 5: Sort by confidence and return ONLY the best one
        signals.sort(key=lambda x: x.confidence, reverse=True)

        # Cap confidence at 1.0
        for s in signals:
            s.confidence = min(s.confidence, 1.0)

        # STRICT: Only return the single best signal (1 layer)
        if signals:
            best = signals[0]
            logger.info(f"Best signal: {best.strategy} {best.direction} (conf: {best.confidence:.2f})")
            return [best]

        logger.info("No valid aligned signals found")
        return signals

    def _is_aligned(self, signal, trend_direction):
        """Check if signal aligns with trend."""
        if trend_direction == 'neutral':
            return True  # All signals ok in neutral
        if signal.direction == 'buy' and trend_direction == 'bullish':
            return True
        if signal.direction == 'sell' and trend_direction == 'bearish':
            return True
        return False

    def get_best_signal(self):
        """Get the single best signal after full analysis."""
        signals = self.analyze()
        if not signals:
            return None

        best = signals[0]

        # Validate minimum confidence
        from config import AI_CONFIG
        if best.confidence < AI_CONFIG['min_confidence']:
            logger.info(f"Best signal confidence ({best.confidence:.2f}) below threshold")
            return None

        # Validate minimum RR
        if best.risk_reward < RISK_CONFIG['rr_minimum']:
            logger.info(f"Best signal RR ({best.risk_reward:.1f}) below minimum")
            return None

        return best
