"""
Position Formatter for AlbraTrading System
멀티 전략 포지션 표시 개선
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime

from src.core.position_manager import Position


@dataclass
class StrategyStyle:
    """전략별 표시 스타일"""
    icon: str
    color: str
    short_name: str
    description: str


class PositionFormatter:
    """포지션 표시 포맷터"""
    
    # 전략별 스타일 정의
    STRATEGY_STYLES = {
        'TFPE': StrategyStyle(
            icon='📊',
            color='#4CAF50',
            short_name='TFPE',
            description='Trend Following with Price Extremes'
        ),
        'ZLMACD_ICHIMOKU': StrategyStyle(
            icon='🌊',
            color='#2196F3',
            short_name='ZL-ICH',
            description='Zero Lag MACD + Ichimoku Cloud'
        ),
        'MOMENTUM': StrategyStyle(
            icon='🚀',
            color='#FF9800',
            short_name='MOM',
            description='Momentum Breakout'
        ),
        'ZLHMA_EMA_CROSS': StrategyStyle(
            icon='📈',
            color='#9C27B0',
            short_name='ZL-EMA',
            description='Zero Lag HMA EMA Cross'
        ),
        'MANUAL': StrategyStyle(
            icon='👤',
            color='#607D8B',
            short_name='MANUAL',
            description='Manual Trading'
        )
    }
    
    # 기본 스타일
    DEFAULT_STYLE = StrategyStyle(
        icon='📈',
        color='#000000',
        short_name='UNKNOWN',
        description='Unknown Strategy'
    )
    
    @classmethod
    def get_strategy_style(cls, strategy_name: Optional[str]) -> StrategyStyle:
        """전략 스타일 가져오기"""
        if not strategy_name:
            strategy_name = 'MANUAL'
        return cls.STRATEGY_STYLES.get(strategy_name, cls.DEFAULT_STYLE)
    
    @classmethod
    def format_telegram_position(cls, position: Position, current_price: Optional[float] = None) -> str:
        """텔레그램용 포지션 포맷
        
        Args:
            position: 포지션 객체
            current_price: 현재 가격 (옵션)
            
        Returns:
            포맷된 문자열
        """
        style = cls.get_strategy_style(position.strategy_name)
        
        # PnL 계산
        if current_price and hasattr(position, 'get_unrealized_pnl'):
            pnl = position.get_unrealized_pnl(current_price)
            pnl_emoji = '🟢' if pnl >= 0 else '🔴'
            pnl_text = f"{pnl_emoji} {pnl:+.2f}%"
        else:
            pnl_text = "N/A"
        
        # 포지션 방향 이모지
        side_emoji = '🔺' if position.side == 'LONG' else '🔻'
        
        # 포맷팅
        return (
            f"{style.icon} <b>{position.symbol}</b> [{style.short_name}]\n"
            f"├ 방향: {side_emoji} {position.side} {position.leverage}x\n"
            f"├ 수량: {position.size:.4f}\n"
            f"├ 진입가: ${position.entry_price:.2f}\n"
            f"├ PnL: {pnl_text}\n"
            f"└ 상태: {position.status}"
        )
    
    @classmethod
    def format_position_summary(cls, positions: List[Position], account_label: Optional[str] = None) -> str:
        """포지션 요약 (전략별 그룹핑)
        
        Args:
            positions: 포지션 리스트
            account_label: 계좌 라벨 (예: "Master", "Sub1")
            
        Returns:
            포맷된 요약 문자열
        """
        if not positions:
            return f"📊 <b>포지션 현황{f' ({account_label})' if account_label else ''}</b>\n\n포지션이 없습니다."
        
        # 전략별 그룹핑
        grouped = {}
        total_pnl = 0.0
        
        for pos in positions:
            strategy = pos.strategy_name or 'MANUAL'
            if strategy not in grouped:
                grouped[strategy] = []
            grouped[strategy].append(pos)
            
            # PnL 합산 (가능한 경우)
            if hasattr(pos, 'unrealized_pnl'):
                total_pnl += getattr(pos, 'unrealized_pnl', 0)
        
        # 요약 생성
        summary = f"📊 <b>포지션 현황{f' ({account_label})' if account_label else ''}</b>\n"
        summary += f"전체: {len(positions)}개 | 총 PnL: {'🟢' if total_pnl >= 0 else '🔴'} {total_pnl:+.2f}%\n\n"
        
        # 전략별 출력
        for strategy, strategy_positions in sorted(grouped.items()):
            style = cls.get_strategy_style(strategy)
            strategy_pnl = sum(getattr(p, 'unrealized_pnl', 0) for p in strategy_positions)
            
            summary += f"{style.icon} <b>{strategy}</b> ({len(strategy_positions)}개)\n"
            
            for pos in strategy_positions:
                pnl = getattr(pos, 'unrealized_pnl', 0)
                pnl_emoji = '🟢' if pnl >= 0 else '🔴'
                side_emoji = '🔺' if pos.side == 'LONG' else '🔻'
                
                summary += f"  • {pos.symbol}: {side_emoji} {pos.side} "
                summary += f"{pnl_emoji} {pnl:+.2f}%\n"
            
            summary += f"  └ 소계: {'🟢' if strategy_pnl >= 0 else '🔴'} {strategy_pnl:+.2f}%\n\n"
        
        return summary.strip()
    
    @classmethod
    def format_position_detail(cls, position: Position, current_price: Optional[float] = None) -> str:
        """포지션 상세 정보 포맷
        
        Args:
            position: 포지션 객체
            current_price: 현재 가격
            
        Returns:
            상세 정보 문자열
        """
        style = cls.get_strategy_style(position.strategy_name)
        
        # 기본 정보
        detail = f"{style.icon} <b>{position.symbol} 포지션 상세</b>\n"
        detail += f"<b>전략:</b> {style.description}\n"
        detail += "─" * 30 + "\n"
        
        # 포지션 정보
        side_emoji = '🔺' if position.side == 'LONG' else '🔻'
        detail += f"<b>기본 정보</b>\n"
        detail += f"• 방향: {side_emoji} {position.side}\n"
        detail += f"• 레버리지: {position.leverage}x\n"
        detail += f"• 수량: {position.size:.4f}\n"
        detail += f"• 진입가: ${position.entry_price:.2f}\n"
        
        # 현재 상태
        if current_price:
            pnl = position.get_unrealized_pnl(current_price) if hasattr(position, 'get_unrealized_pnl') else 0
            pnl_emoji = '🟢' if pnl >= 0 else '🔴'
            
            detail += f"\n<b>현재 상태</b>\n"
            detail += f"• 현재가: ${current_price:.2f}\n"
            detail += f"• 미실현 PnL: {pnl_emoji} {pnl:+.2f}%\n"
        
        # 리스크 관리
        if position.stop_loss or position.take_profit:
            detail += f"\n<b>리스크 관리</b>\n"
            if position.stop_loss:
                detail += f"• 손절가: ${position.stop_loss:.2f}\n"
            if position.take_profit:
                detail += f"• 익절가: ${position.take_profit:.2f}\n"
        
        # 메타 정보
        detail += f"\n<b>메타 정보</b>\n"
        detail += f"• ID: {position.position_id[:8]}...\n"
        detail += f"• 생성: {position.created_at}\n"
        detail += f"• 수정: {position.last_updated}\n"
        detail += f"• 상태: {position.status}\n"
        
        # 태그
        if hasattr(position, 'tags') and position.tags:
            detail += f"• 태그: {', '.join(position.tags)}\n"
        
        return detail
    
    @classmethod
    def format_dashboard_position(cls, position: Position) -> Dict[str, any]:
        """대시보드용 포지션 데이터 포맷
        
        Args:
            position: 포지션 객체
            
        Returns:
            대시보드용 딕셔너리
        """
        style = cls.get_strategy_style(position.strategy_name)
        
        return {
            'symbol': position.symbol,
            'strategy': position.strategy_name or 'MANUAL',
            'strategy_icon': style.icon,
            'strategy_color': style.color,
            'strategy_short': style.short_name,
            'side': position.side,
            'side_color': '#4CAF50' if position.side == 'LONG' else '#F44336',
            'leverage': position.leverage,
            'size': float(position.size),
            'entry_price': float(position.entry_price),
            'current_pnl': float(getattr(position, 'unrealized_pnl', 0)),
            'pnl_color': '#4CAF50' if getattr(position, 'unrealized_pnl', 0) >= 0 else '#F44336',
            'status': position.status,
            'created_at': position.created_at,
            'position_id': position.position_id
        }
    
    @classmethod
    def format_strategy_legend(cls) -> str:
        """전략 범례 생성"""
        legend = "📚 <b>전략 범례</b>\n\n"
        
        for strategy_name, style in cls.STRATEGY_STYLES.items():
            legend += f"{style.icon} <b>{strategy_name}</b> ({style.short_name})\n"
            legend += f"   {style.description}\n\n"
        
        return legend.strip()