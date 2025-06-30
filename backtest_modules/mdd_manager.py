# backtest_modules/mdd_manager.py
"""MDD 관리 기능 모듈"""

class MDDManager:
    """개선된 MDD 관리 클래스"""
    
    def __init__(self, params):
        self.params = params
        self.peak_capital = 0
        self.current_mdd = 0
        self.mdd_restricted = False
        self.consecutive_wins = 0
        self.recovery_mode_active = False
        self.current_recovery_multiplier = 1.0
        self.active_positions_count = 0
        self.time_without_position = 0
        self.mdd_events = []
    
    def calculate_current_mdd(self, current_capital: float) -> float:
        """현재 MDD 계산 및 업데이트"""
        if current_capital > self.peak_capital:
            self.peak_capital = current_capital
            # Peak 갱신 시 회복 모드 해제
            self.recovery_mode_active = False
            self.current_recovery_multiplier = 1.0
        
        self.current_mdd = (self.peak_capital - current_capital) / self.peak_capital * 100
        return self.current_mdd
    
    def get_mdd_position_multiplier(self) -> float:
        """MDD 수준에 따른 포지션 크기 배수 계산"""
        if self.current_mdd >= self.params['mdd_level_4']:
            return self.params['mdd_level_4_size']
        elif self.current_mdd >= self.params['mdd_level_3']:
            return self.params['mdd_level_3_size']
        elif self.current_mdd >= self.params['mdd_level_2']:
            return self.params['mdd_level_2_size']
        elif self.current_mdd >= self.params['mdd_level_1']:
            return self.params['mdd_level_1_size']
        else:
            return 1.0
    
    def check_mdd_restrictions(self) -> dict:
        """개선된 MDD 기반 거래 제한 확인"""
        restrictions = {
            'allow_new_trades': True,
            'position_size_multiplier': 1.0,
            'force_close_positions': False,
            'reason': '',
            'mdd_level': 0
        }
        
        # 긴급 정지 확인
        if self.current_mdd >= self.params['mdd_emergency_stop']:
            restrictions['allow_new_trades'] = False
            restrictions['force_close_positions'] = True
            restrictions['reason'] = f'EMERGENCY STOP: MDD {self.current_mdd:.1f}%'
            return restrictions
        
        # MDD 단계별 포지션 크기 조정
        base_multiplier = self.get_mdd_position_multiplier()
        
        # 회복 모드 적용
        if self.recovery_mode_active and self.params['mdd_recovery_mode']:
            # 회복 중이면 추가 배수 적용
            final_multiplier = min(base_multiplier * self.current_recovery_multiplier, 
                                 self.params['max_recovery_size'])
        else:
            final_multiplier = base_multiplier
        
        restrictions['position_size_multiplier'] = final_multiplier
        
        # MDD 수준 기록
        if self.current_mdd >= self.params['mdd_level_3']:
            restrictions['mdd_level'] = 3
            restrictions['reason'] = f'MDD Level 3: {self.current_mdd:.1f}% (Size: {final_multiplier*100:.0f}%)'
        elif self.current_mdd >= self.params['mdd_level_2']:
            restrictions['mdd_level'] = 2
            restrictions['reason'] = f'MDD Level 2: {self.current_mdd:.1f}% (Size: {final_multiplier*100:.0f}%)'
        elif self.current_mdd >= self.params['mdd_level_1']:
            restrictions['mdd_level'] = 1
            restrictions['reason'] = f'MDD Level 1: {self.current_mdd:.1f}% (Size: {final_multiplier*100:.0f}%)'
        else:
            restrictions['reason'] = f'Normal trading (MDD: {self.current_mdd:.1f}%)'
        
        # 포지션이 없고 MDD가 높은 경우 특별 처리
        if (self.active_positions_count == 0 and 
            self.params['force_trade_if_no_position'] and 
            self.current_mdd >= self.params['mdd_level_2']):
            # 포지션이 없으면 최소한의 거래는 허용
            restrictions['allow_new_trades'] = True
            restrictions['position_size_multiplier'] = max(0.1, final_multiplier * 0.5)  # 최소 10%
            restrictions['reason'] += ' [No position - minimal trading allowed]'
        
        # MDD 상태 변경 이벤트 기록
        if not self.mdd_restricted and restrictions['mdd_level'] >= 1:
            self.mdd_restricted = True
            self.recovery_mode_active = True
            self.mdd_events.append({
                'type': 'mdd_restriction_start',
                'mdd': self.current_mdd,
                'level': restrictions['mdd_level'],
                'capital': self.peak_capital * (1 - self.current_mdd/100)
            })
        elif self.mdd_restricted and self.current_mdd <= self.params['mdd_recovery_threshold']:
            self.mdd_restricted = False
            self.recovery_mode_active = False
            self.current_recovery_multiplier = 1.0
            self.mdd_events.append({
                'type': 'mdd_recovered',
                'mdd': self.current_mdd,
                'capital': self.peak_capital * (1 - self.current_mdd/100)
            })
        
        return restrictions
    
    def update_recovery_status(self, trade_won: bool):
        """거래 결과에 따른 회복 상태 업데이트"""
        if not self.recovery_mode_active:
            return
        
        if trade_won:
            self.consecutive_wins += 1
            # 연속 승리 시 포지션 크기 점진적 증가
            if self.consecutive_wins >= self.params['recovery_win_threshold']:
                self.current_recovery_multiplier = min(
                    self.current_recovery_multiplier + self.params['recovery_size_increment'],
                    self.params['max_recovery_size']
                )
                self.consecutive_wins = 0  # 리셋
                print(f"  🔄 Recovery multiplier increased to {self.current_recovery_multiplier:.1f}")
        else:
            self.consecutive_wins = 0
            # 패배 시 회복 배수 약간 감소 (너무 급격하지 않게)
            self.current_recovery_multiplier = max(
                self.current_recovery_multiplier - self.params['recovery_size_increment'] * 0.5,
                0.1
            )
