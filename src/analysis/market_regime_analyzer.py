"""
Market Regime Analyzer
시장 상태(레진)를 식별하고 전략 파라미터를 동적으로 조정
백테스트에서 검증된 로직을 실제 시스템에 적용
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """시장 레진 타입"""
    STRONG_UPTREND = "STRONG_UPTREND"
    STRONG_DOWNTREND = "STRONG_DOWNTREND"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    RANGE_BOUND = "RANGE_BOUND"
    NORMAL = "NORMAL"


class MarketRegimeAnalyzer:
    """시장 레진 분석기"""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Args:
            config: 레진 분석 설정
        """
        self.config = config or {}
        
        # 레진 판단 임계값
        self.thresholds = {
            'adx_strong_trend': self.config.get('adx_strong_trend', 30),
            'adx_weak_trend': self.config.get('adx_weak_trend', 20),
            'volatility_high': self.config.get('volatility_high', 0.4),  # 연환산 40%
            'atr_pct_high': self.config.get('atr_pct_high', 0.04),      # ATR 4%
            'channel_width_narrow': self.config.get('channel_width_narrow', 0.03),  # 3%
            'momentum_strong': self.config.get('momentum_strong', 0.1),   # 10%
        }
        
        # 레진별 파라미터 조정 규칙
        self.regime_adjustments = {
            MarketRegime.STRONG_UPTREND: {
                'momentum_allocation': 0.7,  # Momentum 전략 우선
                'tfpe_allocation': 0.3,
                'signal_threshold_adjustment': -1,  # 신호 임계값 완화
                'stop_loss_multiplier': 1.0,
                'take_profit_multiplier': 1.2,  # 익절 확대
            },
            MarketRegime.STRONG_DOWNTREND: {
                'momentum_allocation': 0.7,
                'tfpe_allocation': 0.3,
                'signal_threshold_adjustment': -1,
                'stop_loss_multiplier': 1.0,
                'take_profit_multiplier': 1.2,
            },
            MarketRegime.HIGH_VOLATILITY: {
                'momentum_allocation': 0.2,
                'tfpe_allocation': 0.8,  # TFPE 전략 우선
                'signal_threshold_adjustment': 1,  # 신호 임계값 강화
                'stop_loss_multiplier': 0.8,  # 손절 타이트하게
                'take_profit_multiplier': 1.0,
                'max_risk_multiplier': 0.7,  # 리스크 축소
            },
            MarketRegime.RANGE_BOUND: {
                'momentum_allocation': 0.2,
                'tfpe_allocation': 0.8,
                'signal_threshold_adjustment': 0,
                'rsi_oversold_adjustment': 5,   # RSI 극단값 확대
                'rsi_overbought_adjustment': -5,
                'stop_loss_multiplier': 1.0,
                'take_profit_multiplier': 0.8,  # 익절 축소
            },
            MarketRegime.NORMAL: {
                'momentum_allocation': 0.2,  # 백테스트 기본값
                'tfpe_allocation': 0.8,
                'signal_threshold_adjustment': 0,
                'stop_loss_multiplier': 1.0,
                'take_profit_multiplier': 1.0,
            }
        }
        
        # 레진 히스토리
        self.regime_history = []
        self.last_regime_change = None
        
        logger.info("Market Regime Analyzer 초기화 완료")
    
    def identify_market_regime(self, df: pd.DataFrame, lookback_periods: int = 20) -> MarketRegime:
        """시장 레진 식별
        
        Args:
            df: 가격 데이터 (4시간봉 권장)
            lookback_periods: 분석 기간
            
        Returns:
            현재 시장 레진
        """
        try:
            # 데이터 검증
            if len(df) < lookback_periods:
                logger.warning(f"데이터 부족: {len(df)} < {lookback_periods}")
                return MarketRegime.NORMAL
            
            # 최근 데이터
            recent_data = df.iloc[-lookback_periods:]
            
            # 1. 트렌드 강도 (ADX)
            adx_mean = recent_data['adx'].mean() if 'adx' in recent_data.columns else 0
            
            # 2. 변동성 레진
            if 'atr' in recent_data.columns and 'close' in recent_data.columns:
                atr_pct = (recent_data['atr'] / recent_data['close']).mean()
            else:
                atr_pct = 0
            
            # 수익률 기반 변동성
            returns = recent_data['close'].pct_change().dropna()
            realized_vol = returns.std() * np.sqrt(252)  # 연환산
            
            # 3. 모멘텀 스코어
            if len(df) >= lookback_periods:
                momentum_20 = (df['close'].iloc[-1] / df['close'].iloc[-20] - 1)
                momentum_5 = (df['close'].iloc[-1] / df['close'].iloc[-5] - 1)
            else:
                momentum_20 = 0
                momentum_5 = 0
            
            # 4. Donchian Channel 폭
            if 'channel_width_pct' in recent_data.columns:
                channel_width = recent_data['channel_width_pct'].mean()
            elif 'dc_upper' in recent_data.columns and 'dc_lower' in recent_data.columns:
                dc_width = recent_data['dc_upper'] - recent_data['dc_lower']
                channel_width = (dc_width / recent_data['close']).mean()
            else:
                channel_width = 0.05  # 기본값
            
            # 5. 추세 방향 (DI)
            if 'plus_di' in recent_data.columns and 'minus_di' in recent_data.columns:
                di_diff_mean = (recent_data['plus_di'] - recent_data['minus_di']).mean()
            else:
                di_diff_mean = 0
            
            # 레진 판단 로직
            current_regime = self._determine_regime(
                adx_mean, realized_vol, atr_pct, momentum_20, momentum_5,
                channel_width, di_diff_mean
            )
            
            # 레진 변경 기록
            self._record_regime_change(current_regime)
            
            logger.info(f"시장 레진 식별: {current_regime.value}")
            logger.debug(f"  ADX: {adx_mean:.1f}, Vol: {realized_vol:.2%}, "
                        f"ATR%: {atr_pct:.2%}, Momentum: {momentum_20:.2%}")
            
            return current_regime
            
        except Exception as e:
            logger.error(f"시장 레진 식별 실패: {e}")
            return MarketRegime.NORMAL
    
    def _determine_regime(self, adx: float, volatility: float, atr_pct: float,
                         momentum_20: float, momentum_5: float, 
                         channel_width: float, di_diff: float) -> MarketRegime:
        """레진 판단 로직"""
        
        # 강한 추세 체크
        if adx > self.thresholds['adx_strong_trend'] and abs(momentum_20) > self.thresholds['momentum_strong']:
            if momentum_20 > 0 and di_diff > 10:
                return MarketRegime.STRONG_UPTREND
            elif momentum_20 < 0 and di_diff < -10:
                return MarketRegime.STRONG_DOWNTREND
        
        # 고변동성 체크
        if volatility > self.thresholds['volatility_high'] or atr_pct > self.thresholds['atr_pct_high']:
            return MarketRegime.HIGH_VOLATILITY
        
        # 횡보장 체크
        if (channel_width < self.thresholds['channel_width_narrow'] and 
            adx < self.thresholds['adx_weak_trend'] and
            abs(momentum_20) < 0.05):  # 5% 미만 변동
            return MarketRegime.RANGE_BOUND
        
        # 기본값
        return MarketRegime.NORMAL
    
    def _record_regime_change(self, new_regime: MarketRegime):
        """레진 변경 기록"""
        if not self.regime_history or self.regime_history[-1]['regime'] != new_regime:
            self.regime_history.append({
                'regime': new_regime,
                'timestamp': datetime.now(),
                'duration': None
            })
            
            # 이전 레진 기간 계산
            if len(self.regime_history) > 1:
                prev = self.regime_history[-2]
                prev['duration'] = (datetime.now() - prev['timestamp']).total_seconds() / 3600  # 시간
            
            self.last_regime_change = datetime.now()
            logger.info(f"시장 레진 변경: {new_regime.value}")
    
    def adjust_parameters_for_regime(self, base_params: Dict, current_regime: MarketRegime) -> Dict:
        """시장 레진에 따른 파라미터 조정
        
        Args:
            base_params: 기본 전략 파라미터
            current_regime: 현재 시장 레진
            
        Returns:
            조정된 파라미터
        """
        try:
            adjusted_params = base_params.copy()
            adjustments = self.regime_adjustments.get(current_regime, {})
            
            # 전략 할당 조정
            if 'tfpe_allocation' in adjustments:
                adjusted_params['tfpe_strategy'] = adjusted_params.get('tfpe_strategy', {})
                adjusted_params['tfpe_strategy']['allocation'] = adjustments['tfpe_allocation']
            
            if 'momentum_allocation' in adjustments:
                adjusted_params['momentum_strategy'] = adjusted_params.get('momentum_strategy', {})
                adjusted_params['momentum_strategy']['allocation'] = adjustments['momentum_allocation']
            
            # 신호 임계값 조정
            if 'signal_threshold_adjustment' in adjustments and 'signal_threshold' in base_params:
                adjusted_params['signal_threshold'] = max(1, min(5, 
                    base_params['signal_threshold'] + adjustments['signal_threshold_adjustment']))
            
            # 손절/익절 조정
            if 'stop_loss_multiplier' in adjustments and 'stop_loss_atr' in base_params:
                adjusted_params['stop_loss_atr'] = base_params['stop_loss_atr'] * adjustments['stop_loss_multiplier']
            
            if 'take_profit_multiplier' in adjustments and 'take_profit_atr' in base_params:
                adjusted_params['take_profit_atr'] = base_params['take_profit_atr'] * adjustments['take_profit_multiplier']
            
            # RSI 조정 (횡보장)
            if current_regime == MarketRegime.RANGE_BOUND:
                if 'rsi_oversold' in base_params:
                    adjusted_params['rsi_oversold'] = base_params['rsi_oversold'] + adjustments.get('rsi_oversold_adjustment', 0)
                if 'rsi_overbought' in base_params:
                    adjusted_params['rsi_overbought'] = base_params['rsi_overbought'] + adjustments.get('rsi_overbought_adjustment', 0)
            
            # 리스크 조정 (고변동성)
            if 'max_risk_multiplier' in adjustments:
                if 'position_size' in base_params:
                    adjusted_params['position_size'] = base_params['position_size'] * adjustments['max_risk_multiplier']
                if 'leverage' in base_params and adjustments['max_risk_multiplier'] < 1:
                    # 고변동성에서는 레버리지도 축소 고려
                    adjusted_params['leverage'] = max(1, int(base_params['leverage'] * 0.8))
            
            logger.info(f"파라미터 조정 완료 - 레진: {current_regime.value}")
            self._log_adjustments(base_params, adjusted_params)
            
            return adjusted_params
            
        except Exception as e:
            logger.error(f"파라미터 조정 실패: {e}")
            return base_params
    
    def _log_adjustments(self, base_params: Dict, adjusted_params: Dict):
        """조정 내역 로깅"""
        changes = []
        
        # 주요 파라미터 비교
        key_params = ['signal_threshold', 'stop_loss_atr', 'take_profit_atr', 
                     'position_size', 'leverage', 'rsi_oversold', 'rsi_overbought']
        
        for param in key_params:
            if param in base_params and param in adjusted_params:
                if base_params[param] != adjusted_params[param]:
                    changes.append(f"{param}: {base_params[param]} → {adjusted_params[param]}")
        
        if changes:
            logger.info(f"파라미터 변경사항: {', '.join(changes)}")
    
    def get_regime_statistics(self) -> Dict:
        """레진 통계 반환"""
        if not self.regime_history:
            return {}
        
        stats = {
            'current_regime': self.regime_history[-1]['regime'].value if self.regime_history else None,
            'last_change': self.last_regime_change.isoformat() if self.last_regime_change else None,
            'regime_counts': {},
            'average_duration': {},
            'total_regimes': len(self.regime_history)
        }
        
        # 레진별 카운트 및 평균 지속시간
        for record in self.regime_history:
            regime = record['regime'].value
            stats['regime_counts'][regime] = stats['regime_counts'].get(regime, 0) + 1
            
            if record['duration']:
                if regime not in stats['average_duration']:
                    stats['average_duration'][regime] = []
                stats['average_duration'][regime].append(record['duration'])
        
        # 평균 계산
        for regime, durations in stats['average_duration'].items():
            stats['average_duration'][regime] = sum(durations) / len(durations)
        
        return stats
    
    def should_update_regime(self, last_check_time: Optional[datetime] = None,
                           min_interval_minutes: int = 60) -> bool:
        """레진 업데이트 필요 여부 확인
        
        Args:
            last_check_time: 마지막 체크 시간
            min_interval_minutes: 최소 체크 간격 (분)
            
        Returns:
            업데이트 필요 여부
        """
        if last_check_time is None:
            return True
        
        time_since_last = (datetime.now() - last_check_time).total_seconds() / 60
        return time_since_last >= min_interval_minutes
    
    def export_regime_history(self) -> pd.DataFrame:
        """레진 히스토리를 DataFrame으로 내보내기"""
        if not self.regime_history:
            return pd.DataFrame()
        
        data = []
        for record in self.regime_history:
            data.append({
                'regime': record['regime'].value,
                'timestamp': record['timestamp'],
                'duration_hours': record['duration']
            })
        
        return pd.DataFrame(data)


# 전역 인스턴스
_regime_analyzer = None

def get_regime_analyzer(config: Optional[Dict] = None) -> MarketRegimeAnalyzer:
    """싱글톤 레진 분석기 반환"""
    global _regime_analyzer
    if _regime_analyzer is None:
        _regime_analyzer = MarketRegimeAnalyzer(config)
    return _regime_analyzer
