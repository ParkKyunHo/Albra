"""
Risk Parity Allocator - 리스크 패리티 기반 자본 배분
전략 간 리스크를 균등하게 배분하여 포트폴리오 최적화
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import pandas as pd
from collections import defaultdict

from ..utils.logger import setup_logger

logger = setup_logger(__name__)


class RiskParityAllocator:
    """
    리스크 패리티 자본 배분 시스템
    - 각 전략의 변동성 측정
    - 리스크 기여도 균등화
    - 동적 자본 재배분
    """
    
    def __init__(self, performance_tracker):
        self.performance_tracker = performance_tracker
        
        # 리스크 패리티 파라미터
        self.params = {
            'min_history_days': 30,      # 최소 분석 기간
            'max_allocation': 0.5,       # 단일 전략 최대 배분
            'min_allocation': 0.1,       # 단일 전략 최소 배분
            'rebalance_threshold': 0.1,  # 재배분 임계값 (10% 차이)
            'lookback_window': 60,       # 변동성 계산 기간 (일)
            'correlation_penalty': 0.2,   # 상관관계 페널티
            'target_volatility': 0.15    # 목표 연간 변동성 (15%)
        }
        
        # 캐시
        self._allocation_cache = {}
        self._last_calculation = None
        self._volatility_cache = {}
        
        logger.info("Risk Parity Allocator 초기화 완료")
    
    async def calculate_risk_parity_allocation(self, strategies: List[str], 
                                             total_capital: float) -> Dict[str, float]:
        """
        리스크 패리티 기반 자본 배분 계산
        
        Args:
            strategies: 전략 리스트
            total_capital: 총 자본
            
        Returns:
            전략별 배분 금액
        """
        try:
            # 캐시 확인 (1시간)
            if self._last_calculation and datetime.now() - self._last_calculation < timedelta(hours=1):
                if all(s in self._allocation_cache for s in strategies):
                    return {s: self._allocation_cache[s] * total_capital for s in strategies}
            
            # 1. 각 전략의 변동성 계산
            volatilities = await self._calculate_strategy_volatilities(strategies)
            
            # 2. 상관관계 매트릭스 계산
            correlation_matrix = await self._calculate_correlation_matrix(strategies)
            
            # 3. 리스크 패리티 가중치 계산
            weights = self._calculate_risk_parity_weights(volatilities, correlation_matrix)
            
            # 4. 제약조건 적용
            weights = self._apply_constraints(weights, strategies)
            
            # 5. 최종 배분
            allocations = {}
            for strategy, weight in zip(strategies, weights):
                allocations[strategy] = weight * total_capital
                self._allocation_cache[strategy] = weight
            
            self._last_calculation = datetime.now()
            
            # 로깅
            logger.info("리스크 패리티 배분 계산 완료:")
            for strategy, amount in allocations.items():
                pct = (amount / total_capital) * 100
                vol = volatilities.get(strategy, 0) * 100
                logger.info(f"  {strategy}: ${amount:,.0f} ({pct:.1f}%), 변동성: {vol:.1f}%")
            
            return allocations
            
        except Exception as e:
            logger.error(f"리스크 패리티 계산 실패: {e}")
            # 균등 배분 폴백
            equal_weight = 1.0 / len(strategies)
            return {s: equal_weight * total_capital for s in strategies}
    
    async def _calculate_strategy_volatilities(self, strategies: List[str]) -> Dict[str, float]:
        """전략별 변동성 계산"""
        volatilities = {}
        
        for strategy in strategies:
            try:
                # 캐시 확인
                cache_key = f"{strategy}_vol"
                if cache_key in self._volatility_cache:
                    last_update = self._volatility_cache[cache_key].get('timestamp', datetime.min)
                    if datetime.now() - last_update < timedelta(hours=6):
                        volatilities[strategy] = self._volatility_cache[cache_key]['value']
                        continue
                
                # 최근 거래 기록
                trades = self.performance_tracker.get_recent_trades(strategy, limit=100)
                
                if len(trades) < 10:
                    # 거래 부족시 기본 변동성
                    volatilities[strategy] = 0.2  # 20%
                    continue
                
                # 일일 수익률 계산
                daily_returns = self._extract_daily_returns(trades)
                
                if len(daily_returns) > 1:
                    # 연간화 변동성
                    vol = np.std(daily_returns) * np.sqrt(252)
                    volatilities[strategy] = vol
                    
                    # 캐시 저장
                    self._volatility_cache[cache_key] = {
                        'value': vol,
                        'timestamp': datetime.now()
                    }
                else:
                    volatilities[strategy] = 0.2
                    
            except Exception as e:
                logger.error(f"{strategy} 변동성 계산 실패: {e}")
                volatilities[strategy] = 0.2  # 기본값
        
        return volatilities
    
    def _extract_daily_returns(self, trades) -> List[float]:
        """거래 기록에서 일일 수익률 추출"""
        daily_pnl = defaultdict(float)
        
        for trade in trades:
            date = trade.exit_time.date()
            daily_pnl[date] += trade.pnl_pct / 100  # 퍼센트를 비율로
        
        # 날짜순 정렬
        dates = sorted(daily_pnl.keys())
        returns = [daily_pnl[date] for date in dates]
        
        return returns
    
    async def _calculate_correlation_matrix(self, strategies: List[str]) -> np.ndarray:
        """전략 간 상관관계 매트릭스 계산"""
        n = len(strategies)
        
        # 데이터 부족시 단위 행렬 (상관관계 없음 가정)
        if n == 1:
            return np.array([[1.0]])
        
        try:
            # 각 전략의 일일 수익률 시계열
            returns_data = {}
            
            for strategy in strategies:
                trades = self.performance_tracker.get_recent_trades(strategy, limit=200)
                if len(trades) > 10:
                    daily_returns = self._extract_daily_returns_series(trades)
                    returns_data[strategy] = daily_returns
            
            if len(returns_data) < 2:
                # 데이터 부족
                return np.eye(n)
            
            # DataFrame으로 변환
            df = pd.DataFrame(returns_data)
            
            # 상관관계 계산
            correlation = df.corr().fillna(0).values
            
            # 대각선은 1로 보정
            np.fill_diagonal(correlation, 1.0)
            
            return correlation
            
        except Exception as e:
            logger.error(f"상관관계 계산 실패: {e}")
            return np.eye(n)
    
    def _extract_daily_returns_series(self, trades) -> pd.Series:
        """거래에서 일일 수익률 시계열 추출"""
        daily_pnl = {}
        
        for trade in trades:
            date = trade.exit_time.date()
            if date not in daily_pnl:
                daily_pnl[date] = 0
            daily_pnl[date] += trade.pnl_pct / 100
        
        # Series로 변환
        series = pd.Series(daily_pnl)
        series.index = pd.to_datetime(series.index)
        
        # 일일 수익률로 리샘플링
        daily_returns = series.resample('D').sum()
        
        return daily_returns
    
    def _calculate_risk_parity_weights(self, volatilities: Dict[str, float], 
                                     correlation: np.ndarray) -> np.ndarray:
        """리스크 패리티 가중치 계산"""
        strategies = list(volatilities.keys())
        n = len(strategies)
        
        # 변동성 벡터
        vols = np.array([volatilities[s] for s in strategies])
        
        # 공분산 행렬 = 상관관계 * 변동성
        cov_matrix = correlation * np.outer(vols, vols)
        
        # 초기 가중치 (균등)
        weights = np.ones(n) / n
        
        # 반복적 최적화 (뉴턴-랩슨)
        for _ in range(100):
            # 포트폴리오 변동성
            port_vol = np.sqrt(weights @ cov_matrix @ weights)
            
            # 각 자산의 리스크 기여도
            marginal_contrib = cov_matrix @ weights / port_vol
            risk_contrib = weights * marginal_contrib
            
            # 목표: 모든 자산의 리스크 기여도를 균등하게
            target_contrib = port_vol / n
            
            # 가중치 업데이트
            adjustment = (target_contrib - risk_contrib) / marginal_contrib
            weights = weights + 0.1 * adjustment  # 학습률 0.1
            
            # 정규화
            weights = np.maximum(weights, 0)  # 음수 방지
            weights = weights / weights.sum()
            
            # 수렴 체크
            if np.max(np.abs(risk_contrib - target_contrib)) < 0.001:
                break
        
        return weights
    
    def _apply_constraints(self, weights: np.ndarray, strategies: List[str]) -> np.ndarray:
        """제약조건 적용"""
        # 최소/최대 배분 제약
        weights = np.maximum(weights, self.params['min_allocation'])
        weights = np.minimum(weights, self.params['max_allocation'])
        
        # 정규화
        weights = weights / weights.sum()
        
        return weights
    
    def should_rebalance(self, current_allocations: Dict[str, float], 
                        target_allocations: Dict[str, float]) -> bool:
        """재배분 필요 여부 판단"""
        if not current_allocations or not target_allocations:
            return True
        
        total_current = sum(current_allocations.values())
        total_target = sum(target_allocations.values())
        
        for strategy in target_allocations:
            if strategy not in current_allocations:
                return True
            
            current_weight = current_allocations[strategy] / total_current
            target_weight = target_allocations[strategy] / total_target
            
            # 임계값 이상 차이
            if abs(current_weight - target_weight) > self.params['rebalance_threshold']:
                return True
        
        return False
    
    def get_position_size_multiplier(self, strategy: str, base_size: float, 
                                   total_capital: float) -> float:
        """리스크 패리티 기반 포지션 크기 배수"""
        try:
            # 캐시된 배분 비율
            if strategy in self._allocation_cache:
                allocation_pct = self._allocation_cache[strategy]
                
                # 기본 크기 대비 조정 배수
                base_allocation = base_size / total_capital
                multiplier = allocation_pct / base_allocation
                
                # 합리적 범위로 제한
                multiplier = max(0.5, min(2.0, multiplier))
                
                return multiplier
            
            return 1.0  # 기본값
            
        except Exception as e:
            logger.error(f"포지션 크기 배수 계산 실패: {e}")
            return 1.0
    
    async def get_allocation_summary(self, strategies: List[str]) -> Dict[str, Dict]:
        """배분 요약 정보"""
        summary = {}
        
        for strategy in strategies:
            volatility = self._volatility_cache.get(f"{strategy}_vol", {}).get('value', 0)
            allocation = self._allocation_cache.get(strategy, 0)
            
            # 성과 지표
            metrics = await self.performance_tracker.get_performance_metrics(strategy)
            
            summary[strategy] = {
                'allocation_pct': f"{allocation * 100:.1f}%",
                'volatility': f"{volatility * 100:.1f}%",
                'sharpe_ratio': round(metrics.sharpe_ratio, 2) if metrics else 0,
                'win_rate': f"{metrics.win_rate:.1%}" if metrics else "N/A",
                'risk_contribution': f"{allocation * volatility:.3f}"
            }
        
        return summary


# 전역 인스턴스
_risk_parity_allocator: Optional[RiskParityAllocator] = None


def get_risk_parity_allocator(performance_tracker) -> RiskParityAllocator:
    """싱글톤 Risk Parity Allocator 반환"""
    global _risk_parity_allocator
    if _risk_parity_allocator is None:
        _risk_parity_allocator = RiskParityAllocator(performance_tracker)
    return _risk_parity_allocator
