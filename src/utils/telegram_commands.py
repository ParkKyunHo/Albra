# src/utils/telegram_commands.py
import os
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, List, Callable
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

logger = logging.getLogger(__name__)

# 이벤트 로거 import 추가
try:
    from src.core.event_logger import get_event_logger
    EVENT_LOGGER_AVAILABLE = True
except ImportError:
    EVENT_LOGGER_AVAILABLE = False
    logger.warning("이벤트 로거 모듈을 찾을 수 없습니다")

# Phase2 Fix 헬퍼 import 추가
try:
    from src.utils.telegram_commands_phase2_fix import MultiAccountStatusHelper
    PHASE2_FIX_AVAILABLE = True
except ImportError:
    PHASE2_FIX_AVAILABLE = False
    logger.warning("Phase2 Fix 헬퍼를 찾을 수 없습니다")


class CommandConfig:
    """명령어 설정 클래스"""
    
    # 명령어 그룹
    STATUS_COMMANDS = ['status', 'balance', 'positions']
    CONTROL_COMMANDS = ['stop_bot', 'resume_bot', 'shutdown']
    PAUSE_COMMANDS = ['pause', 'resume', 'paused']
    SAFETY_COMMANDS = ['continue', 'close_all', 'resume_all']
    SYNC_COMMANDS = ['sync', 'refresh']
    MONITORING_COMMANDS = ['events', 'sync_status']
    PHASE2_COMMANDS = ['phase2_status', 'reconcile', 'position_states', 'discrepancies']
    MANUAL_TRADE_COMMANDS = ['manual', 'close_manual', 'manual_positions', 'modify_manual']
    STRATEGY_COMMANDS = ['strategies', 'pause_strategy', 'resume_strategy', 'strategy_status']
    ACCOUNT_COMMANDS = ['accounts', 'account_status']
    
    # 실시간 동기화가 필요한 명령어
    FORCE_SYNC_COMMANDS = STATUS_COMMANDS + ['sync', 'refresh']
    
    # 명령어 설명
    COMMAND_DESCRIPTIONS = {
        'start': '시작 메시지',
        'help': '도움말 표시',
        'status': '봇 실행 상태 (실시간)',
        'balance': '계좌 잔고 (실시간)',
        'positions': '활성 포지션 (실시간)',
        'stop_bot': '봇 일시 정지',
        'resume_bot': '봇 재시작',
        'shutdown': '시스템 종료',
        'pause': '특정 심볼 일시정지',
        'resume': '특정 심볼 재개',
        'paused': '일시정지된 심볼 목록',
        'continue': '정상 거래 계속',
        'close_all': '모든 시스템 포지션 청산',
        'resume_all': '모든 전략 재개',
        'sync': '강제 동기화',
        'refresh': '강제 동기화 (별칭)',
        'events': '이벤트 요약 확인',
        'sync_status': '포지션 동기화 상태',
        'phase2_status': 'Phase 2 컴포넌트 상태',
        'reconcile': '정합성 확인 실행',
        'position_states': '포지션 상태 머신 조회',
        'discrepancies': '불일치 이력 조회',
        'manual': '수동 거래 등록',
        'close_manual': '수동 포지션 청산',
        'manual_positions': '수동 포지션 목록',
        'modify_manual': '수동 포지션 SL/TP 수정',
        'strategies': '전략 목록 및 상태',
        'pause_strategy': '특정 전략 일시정지',
        'resume_strategy': '특정 전략 재개',
        'strategy_status': '전략별 상세 상태',
        'accounts': '계좌별 현황',
        'account_status': '특정 계좌 상세 상태',
        'fix_positions': '포지션 인식 문제 수정'
    }


class TelegramCommands:
    """텔레그램 명령어 처리 - 실시간 동기화 및 중복 코드 제거"""
    
    def __init__(self, bot_token: str, trading_system):
        self.bot_token = bot_token
        self.trading_system = trading_system
        self.application: Optional[Application] = None
        self.authorized_users = []
        
        # 명령어 핸들러 매핑
        self.command_handlers = self._create_command_handlers()
        
        # 통계
        self.stats = {
            'commands_executed': 0,
            'commands_failed': 0,
            'last_command': None
        }
        
        logger.info(f"텔레그램 명령어 봇 초기화 - 토큰: {bot_token[:10]}...")
    
    def _create_command_handlers(self) -> Dict[str, Callable]:
        """명령어 핸들러 매핑 생성"""
        return {
            'start': self.cmd_start,
            'help': self.cmd_help,
            'status': self.cmd_status,
            'balance': self.cmd_balance,
            'positions': self.cmd_positions,
            'stop_bot': self.cmd_stop_bot,
            'resume_bot': self.cmd_resume_bot,
            'shutdown': self.cmd_shutdown,
            'pause': self.cmd_pause,
            'resume': self.cmd_resume,
            'paused': self.cmd_paused,
            'continue': self.cmd_continue,
            'close_all': self.cmd_close_all,
            'resume_all': self.cmd_resume_all,
            'sync': self.cmd_force_sync,
            'refresh': self.cmd_force_sync,
            'events': self.cmd_events,
            'sync_status': self.cmd_sync_status,
            'phase2_status': self.cmd_phase2_status,
            'reconcile': self.cmd_reconcile,
            'position_states': self.cmd_position_states,
            'discrepancies': self.cmd_discrepancies,
            'manual': self.cmd_manual_trade,
            'close_manual': self.cmd_close_manual,
            'manual_positions': self.cmd_manual_positions,
            'modify_manual': self.cmd_modify_manual,
            'strategies': self.cmd_strategies,
            'pause_strategy': self.cmd_pause_strategy,
            'resume_strategy': self.cmd_resume_strategy,
            'strategy_status': self.cmd_strategy_status,
            'accounts': self.cmd_accounts,
            'account_status': self.cmd_account_status,
            'fix_positions': self.cmd_fix_positions
        }
    
    async def initialize(self) -> bool:
        """봇 초기화"""
        try:
            # HTTPXRequest로 연결 풀 설정 증가
            request = HTTPXRequest(
                connection_pool_size=20,  # 기본값 10에서 증가
                pool_timeout=30.0,        # 기본값 10에서 증가
                connect_timeout=10.0,
                read_timeout=20.0
            )
            
            # 애플리케이션 생성
            self.application = Application.builder()\
                .token(self.bot_token)\
                .request(request)\
                .build()
            
            # 핸들러 등록
            self._register_handlers()
            
            # 봇 정보 확인
            bot = await self.application.bot.get_me()
            logger.info(f"텔레그램 봇 초기화 성공: @{bot.username}")
            
            # 인증된 사용자 로드
            self._load_authorized_users()
            
            return True
            
        except Exception as e:
            logger.error(f"텔레그램 봇 초기화 실패: {e}")
            return False
    
    def _register_handlers(self):
        """핸들러 등록"""
        for command, handler in self.command_handlers.items():
            self.application.add_handler(CommandHandler(command, self._wrap_handler(handler)))
    
    def _wrap_handler(self, handler: Callable):
        """핸들러 래퍼 (에러 처리 및 통계)"""
        async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
            command_name = update.message.text.split()[0][1:]  # /제거
            self.stats['last_command'] = command_name
            
            try:
                await handler(update, context)
                self.stats['commands_executed'] += 1
            except Exception as e:
                logger.error(f"{command_name} 명령어 오류: {e}")
                self.stats['commands_failed'] += 1
                await update.message.reply_text(f"❌ 명령어 실행 중 오류가 발생했습니다: {str(e)}")
        
        return wrapped
    
    def _load_authorized_users(self):
        """인증된 사용자 로드"""
        self.authorized_users = []
        
        # 환경변수에서 로드
        env_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        if env_chat_id:
            try:
                self.authorized_users.append(int(env_chat_id))
            except ValueError:
                logger.error(f"잘못된 TELEGRAM_CHAT_ID: {env_chat_id}")
        
        # config에서 로드
        if hasattr(self.trading_system, 'config'):
            telegram_config = self.trading_system.config.get('telegram', {})
            config_chat_id = telegram_config.get('chat_id')
            if config_chat_id and int(config_chat_id) not in self.authorized_users:
                self.authorized_users.append(int(config_chat_id))
        
        logger.info(f"인증된 사용자: {self.authorized_users}")
    
    def _check_auth(self, update: Update) -> bool:
        """사용자 인증 체크"""
        user_id = update.effective_user.id
        
        if not self.authorized_users or user_id in self.authorized_users:
            return True
        
        logger.warning(f"미인증 사용자 접근 시도: {user_id}")
        return False
    
    async def _force_sync_before_command(self, command_name: str):
        """명령어 실행 전 강제 동기화 - 에러 처리 개선"""
        if command_name not in CommandConfig.FORCE_SYNC_COMMANDS:
            return
        
        try:
            logger.info(f"명령어 '{command_name}' 실행 전 실시간 동기화 시작")
            
            if not hasattr(self.trading_system, 'position_manager'):
                logger.error("position_manager가 없습니다")
                return
            
            # 포지션 동기화 실행
            sync_report = await self.trading_system.position_manager.sync_positions()
            
            # 동기화 결과 처리
            await self._process_sync_report(sync_report)
            
            # 동기화 에러 확인 (추가)
            if sync_report.get('errors'):
                error_count = len(sync_report['errors'])
                error_msg = f"⚠️ 동기화 중 {error_count}개의 오류 발생:\n"
                
                # 처음 3개의 에러만 표시
                for i, error in enumerate(sync_report['errors'][:3]):
                    error_msg += f"• {error}\n"
                
                if error_count > 3:
                    error_msg += f"... 외 {error_count - 3}개"
                
                # 사용자에게 알림
                if self.authorized_users:
                    await self.application.bot.send_message(
                        chat_id=self.authorized_users[0],
                        text=error_msg,
                        parse_mode='HTML'
                    )
            
        except Exception as e:
            logger.error(f"실시간 동기화 실패: {e}")
            
            # 사용자에게 에러 알림 (추가)
            if self.authorized_users:
                error_msg = (
                    "❌ <b>동기화 실패</b>\n\n"
                    f"오류: {str(e)}\n\n"
                    "수동으로 /sync 명령어를 실행해보세요."
                )
                
                try:
                    await self.application.bot.send_message(
                        chat_id=self.authorized_users[0],
                        text=error_msg,
                        parse_mode='HTML'
                    )
                except Exception as notify_error:
                    logger.error(f"에러 알림 전송 실패: {notify_error}")
    
    async def _process_sync_report(self, sync_report: Dict):
        """동기화 리포트 처리"""
        # 새로운 수동 포지션
        if sync_report.get('new_manual'):
            await self._notify_new_manual_positions(sync_report['new_manual'])
        
        # 포지션 변경
        if sync_report.get('size_changed'):
            await self._notify_position_changes(sync_report['size_changed'])
        
        logger.info(
            f"동기화 완료: 신규={len(sync_report.get('new_manual', []))}, "
            f"변경={len(sync_report.get('size_changed', []))}"
        )
    
    async def _notify_new_manual_positions(self, new_symbols: List[str]):
        """새로운 수동 포지션 알림"""
        if not new_symbols or not self.authorized_users:
            return
        
        try:
            message_lines = ["🔍 <b>실시간 감지: 새로운 수동 포지션</b>\n"]
            
            for symbol in new_symbols:
                position = self.trading_system.position_manager.get_position(symbol)
                if position:
                    # 포지션 정보 포맷팅
                    info = await self._format_position_info(position)
                    message_lines.append(info)
            
            message_lines.append("\n✅ 시스템이 자동으로 모니터링을 시작합니다.")
            
            await self.application.bot.send_message(
                chat_id=self.authorized_users[0],
                text='\n'.join(message_lines),
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"새 수동 포지션 알림 실패: {e}")
    
    async def _notify_position_changes(self, changes: List[Dict]):
        """포지션 변경 알림"""
        if not changes or not self.authorized_users:
            return
        
        # 중요한 변경사항만 필터링 (10% 이상)
        significant_changes = [c for c in changes if c.get('change_ratio', 0) > 0.1]
        
        if not significant_changes:
            return
        
        try:
            message_lines = ["⚡ <b>실시간 감지: 포지션 변경</b>\n"]
            
            for change in significant_changes:
                change_type = "🔴 부분 청산" if change['new_size'] < change['old_size'] else "🔵 포지션 증가"
                
                message_lines.append(
                    f"{change_type} <b>{change['symbol']}</b>\n"
                    f"├ {change['old_size']:.4f} → {change['new_size']:.4f}\n"
                    f"└ 변화율: {change['change_ratio']*100:.1f}%\n"
                )
            
            await self.application.bot.send_message(
                chat_id=self.authorized_users[0],
                text='\n'.join(message_lines),
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"포지션 변경 알림 실패: {e}")
    
    async def _format_position_info(self, position) -> str:
        """포지션 정보 포맷팅"""
        try:
            # 현재가 조회
            current_price = await self.trading_system.binance_api.get_current_price(position.symbol)
            
            # 손익 계산
            pnl_percent = 0
            if current_price and position.entry_price:
                if position.side == 'LONG':
                    pnl_percent = (current_price - position.entry_price) / position.entry_price * 100
                else:
                    pnl_percent = (position.entry_price - current_price) / position.entry_price * 100
                pnl_percent *= position.leverage
            
            # 포맷 문자열 수정 - format 메서드 사용
            return """📊 <b>{symbol}</b>
├ 방향: {side}
├ 크기: {size:.4f}
├ 진입가: ${entry_price:.2f}
├ 현재가: ${current_price}
├ 손익: {pnl:+.2f}%
└ 레버리지: {leverage}x
""".format(
                symbol=position.symbol,
                side=position.side,
                size=position.size,
                entry_price=position.entry_price,
                current_price=f"{current_price:.2f}" if current_price else "N/A",
                pnl=pnl_percent,
                leverage=position.leverage
            )
        except Exception as e:
            logger.error(f"포지션 정보 포맷팅 실패: {e}")
            return f"📊 {position.symbol} - 정보 조회 실패\n└ 타입: {'🤖 시스템' if not position.is_manual else '👤 수동'}"
    
    async def _get_system_status(self) -> Dict:
        """시스템 상태 수집 (개선된 버전)"""
        status = {
            'is_running': self.trading_system.is_running,
            'start_time': getattr(self.trading_system, 'start_time', None),
            'uptime': None,
            'position_summary': {},
            'strategy_info': {},
            'safety_status': {},
            'account_balance': 0,
            'multi_account_mode': False,
            'sub_accounts': {}
        }
        
        # 업타임 계산
        if status['start_time']:
            status['uptime'] = datetime.now() - status['start_time']
        
        # 포지션 정보
        if hasattr(self.trading_system, 'position_manager'):
            status['position_summary'] = self.trading_system.position_manager.get_position_summary()
        
        # 전략 정보 개선
        if hasattr(self.trading_system, 'strategies') and self.trading_system.strategies:
            strategy_details = []
            for strategy in self.trading_system.strategies:
                detail = {
                    'name': getattr(strategy, 'name', 'Unknown'),
                    'status': 'PAUSED' if getattr(strategy, 'is_paused', False) else 'RUNNING',
                    'account': getattr(strategy, 'account_name', 'MAIN')
                }
                # 전략별 포지션 수 계산
                if hasattr(self.trading_system.position_manager, 'get_positions_by_strategy'):
                    positions = self.trading_system.position_manager.get_positions_by_strategy(detail['name'])
                    detail['position_count'] = len([p for p in positions if p.status == 'ACTIVE'])
                else:
                    detail['position_count'] = status['position_summary'].get('strategy_counts', {}).get(detail['name'], 0)
                strategy_details.append(detail)
            status['strategy_details'] = strategy_details
        
        # 안전 상태
        if hasattr(self.trading_system, 'safety_checker') and self.trading_system.safety_checker:
            if hasattr(self.trading_system.safety_checker, 'get_status'):
                status['safety_status'] = self.trading_system.safety_checker.get_status()
            else:
                status['safety_status'] = {'safe_mode': getattr(self.trading_system.safety_checker, 'safe_mode', False)}
        
        # 계좌 잔고
        try:
            status['account_balance'] = await self.trading_system.binance_api.get_account_balance()
        except:
            pass
        
        # 멀티계좌 상태 확인
        config = self.trading_system.config
        multi_account_config = config.get('multi_account', {})
        status['multi_account_mode'] = (
            multi_account_config.get('enabled', False) and 
            multi_account_config.get('mode', 'single') == 'multi'
        )
        
        # 서브계좌 정보 (있는 경우)
        if status['multi_account_mode']:
            sub_accounts = multi_account_config.get('sub_accounts', {})
            for acc_id, acc_config in sub_accounts.items():
                if acc_config.get('enabled', False):
                    status['sub_accounts'][acc_id] = {
                        'strategy': acc_config.get('strategy', 'N/A'),
                        'balance': 0  # TODO: 실제 잔고 조회 구현 필요
                    }
        
        return status
    
    # ===== 명령어 핸들러 =====
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """시작 명령어"""
        if not self._check_auth(update):
            await update.message.reply_text("⛔ 권한이 없습니다")
            return
        
        welcome_msg = """
🤖 <b>바이낸스 트레이딩 봇</b>

TFPE (Trend Following Pullback Entry) 전략으로
24/7 자동 거래를 수행합니다.

✨ <b>실시간 동기화 지원</b>
수동 거래 시 즉시 감지 및 알림!

/help - 명령어 목록
/status - 현재 상태 (실시간)
/sync - 즉시 동기화
"""
        
        await update.message.reply_text(welcome_msg, parse_mode='HTML')
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """도움말 표시"""
        if not self._check_auth(update):
            return
        
        help_sections = [
            ("📊 상태 확인 (실시간)", CommandConfig.STATUS_COMMANDS),
            ("⚙️ 제어", CommandConfig.CONTROL_COMMANDS),
            ("🔄 스마트 재개", CommandConfig.PAUSE_COMMANDS),
            ("🛡️ 안전 체크", CommandConfig.SAFETY_COMMANDS),
            ("🔄 동기화", CommandConfig.SYNC_COMMANDS),
            ("📊 모니터링", CommandConfig.MONITORING_COMMANDS),
            ("🚀 Phase 2", CommandConfig.PHASE2_COMMANDS),
            ("🔵 수동 거래", CommandConfig.MANUAL_TRADE_COMMANDS),
            ("🧠 전략 관리", CommandConfig.STRATEGY_COMMANDS),
            ("💼 계좌 관리", CommandConfig.ACCOUNT_COMMANDS)
        ]
        
        help_text = "🤖 <b>바이낸스 트레이딩 봇 명령어</b>\n\n"
        
        for section_name, commands in help_sections:
            help_text += f"<b>{section_name}</b>\n"
            for cmd in commands:
                description = CommandConfig.COMMAND_DESCRIPTIONS.get(cmd, '')
                help_text += f"/{cmd} - {description}\n"
            help_text += "\n"
        
        help_text += """<b>✨ 실시간 기능</b>
- 수동 포지션 진입 시 즉시 감지 및 알림
- 포지션 변경 시 실시간 업데이트
- 모든 상태 명령어에서 즉시 동기화

<b>ℹ️ 정보</b>
/help - 도움말"""
        
        await update.message.reply_text(help_text, parse_mode='HTML')
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """시스템 상태 확인"""
        if not self._check_auth(update):
            return
        
        # 로딩 메시지
        status_msg = await update.message.reply_text("🔄 실시간 상태 확인 중...")
        
        # 실시간 동기화
        await self._force_sync_before_command('status')
        
        # 상태 수집
        status = await self._get_system_status()
        
        # 상태 메시지 생성
        status_text = f"""
📊 <b>실시간 시스템 상태</b>
🕒 업데이트: {datetime.now().strftime('%H:%M:%S')}

<b>🚀 실행 상태:</b> {'✅ 실행 중' if status['is_running'] else '❌ 정지'}
<b>⏱️ 가동 시간:</b> {self._format_uptime(status['uptime'])}
<b>💰 계좌 잔고:</b> ${status['account_balance']:.2f} USDT

<b>🛡️ 안전 모드:</b> {'✅ 활성' if status['safety_status'].get('safe_mode', False) else '❌ 비활성'}

<b>📈 포지션 현황</b>
총 포지션: {status['position_summary'].get('total_positions', 0)}개
├ 시스템: {status['position_summary'].get('auto_positions', 0)}개
├ 수동: {status['position_summary'].get('manual_positions', 0)}개
├ 롱: {status['position_summary'].get('long_positions', 0)}개
└ 숏: {status['position_summary'].get('short_positions', 0)}개
"""
        
        # 전략 상태 추가 (개선된 버전)
        if hasattr(self.trading_system, 'strategies') and self.trading_system.strategies:
            status_text += "\n<b>🧠 전략 상태</b>\n"
            
            # 새로운 strategy_details 사용
            if 'strategy_details' in status:
                for detail in status['strategy_details']:
                    strategy_name = detail['name']
                    strategy_status = '⏸️ 일시정지' if detail['status'] == 'PAUSED' else '▶️ 실행중'
                    position_count = detail['position_count']
                    account_name = detail.get('account', 'MAIN')
                    
                    status_text += f"├ {strategy_name}: {strategy_status} (포지션: {position_count})\n"
                    if status['multi_account_mode'] and account_name != 'MAIN':
                        status_text += f"│  └ 계좌: {account_name}\n"
            else:
                # 호환성을 위한 기존 코드
                for strategy in self.trading_system.strategies:
                    strategy_name = getattr(strategy, 'name', 'Unknown')
                    strategy_positions = status['position_summary'].get('strategy_counts', {}).get(strategy_name, 0)
                    
                    if hasattr(strategy, 'is_paused'):
                        strategy_status = '⏸️ 일시정지' if strategy.is_paused else '▶️ 실행중'
                    else:
                        strategy_status = '▶️ 실행중'
                    
                    status_text += f"├ {strategy_name}: {strategy_status} (포지션: {strategy_positions})\n"
        
        # 멀티계좌 상태 표시 (개선된 버전)
        if status['multi_account_mode']:
            status_text += "\n<b>💼 멀티계좌 모드 활성</b>\n"
            if status['sub_accounts']:
                status_text += "마스터 + "
                status_text += f"{len(status['sub_accounts'])}개 서브계좌\n"
                
                # 서브계좌 상세 (있는 경우)
                for acc_id, acc_info in status['sub_accounts'].items():
                    status_text += f"├ {acc_id}: {acc_info['strategy']}\n"
        
        status_text += "\n<i>💡 실시간 동기화로 최신 정보를 표시합니다</i>"
        
        await status_msg.edit_text(status_text, parse_mode='HTML')
    
    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """계좌 잔고 확인"""
        if not self._check_auth(update):
            return
        
        balance_msg = await update.message.reply_text("💰 실시간 잔고 확인 중...")
        
        await self._force_sync_before_command('balance')
        
        try:
            account_info = await self.trading_system.binance_api.get_account_info()
            
            if account_info:
                total_balance = float(account_info.get('totalWalletBalance', 0))
                unrealized_pnl = float(account_info.get('totalUnrealizedProfit', 0))
                margin_balance = float(account_info.get('totalMarginBalance', 0))
                available_balance = float(account_info.get('availableBalance', 0))
                
                # 수익률 계산
                profit_rate = (unrealized_pnl / total_balance * 100) if total_balance > 0 else 0
                
                balance_text = f"""
💰 <b>실시간 계좌 잔고</b>
🕒 업데이트: {datetime.now().strftime('%H:%M:%S')}

<b>총 잔고:</b> ${total_balance:.2f} USDT
<b>미실현 손익:</b> ${unrealized_pnl:+.2f} USDT
<b>마진 잔고:</b> ${margin_balance:.2f} USDT  
<b>사용 가능:</b> ${available_balance:.2f} USDT

<b>수익률:</b> {profit_rate:+.2f}%

<i>💡 실시간 바이낸스 데이터</i>
"""
            else:
                balance_text = "❌ 계좌 정보를 가져올 수 없습니다."
            
            await balance_msg.edit_text(balance_text, parse_mode='HTML')
            
        except Exception as e:
            await balance_msg.edit_text(f"❌ 잔고 조회 실패: {e}")
    
    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """활성 포지션 목록"""
        if not self._check_auth(update):
            return
        
        pos_msg = await update.message.reply_text("📊 실시간 포지션 확인 중...")
        
        await self._force_sync_before_command('positions')
        
        positions = self.trading_system.position_manager.get_active_positions()
        
        if not positions:
            await pos_msg.edit_text("📊 활성 포지션이 없습니다")
            return
        
        # 포지션 정보 생성
        message_lines = [
            f"📊 <b>실시간 활성 포지션</b>",
            f"🕒 업데이트: {datetime.now().strftime('%H:%M:%S')}\n"
        ]
        
        for pos in positions:
            try:
                pos_info = await self._format_position_info(pos)
                
                # 포지션 타입 추가
                pos_info = pos_info.rstrip() + f"\n└ 타입: {'🤖 시스템' if not pos.is_manual else '👤 수동'}\n"
                message_lines.append(pos_info)
            except Exception as e:
                logger.error(f"포지션 정보 처리 실패 ({pos.symbol}): {e}")
                message_lines.append(f"📊 {pos.symbol} - 정보 조회 실패\n└ 타입: {'🤖 시스템' if not pos.is_manual else '👤 수동'}\n")
        
        message_lines.append("<i>💡 실시간 가격으로 계산된 손익</i>")
        
        await pos_msg.edit_text('\n'.join(message_lines), parse_mode='HTML')
    
    async def cmd_force_sync(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """강제 동기화"""
        if not self._check_auth(update):
            return
        
        sync_msg = await update.message.reply_text("🔄 강제 동기화 실행 중...")
        
        start_time = datetime.now()
        
        # 동기화 실행
        sync_report = await self.trading_system.position_manager.sync_positions()
        
        sync_duration = (datetime.now() - start_time).total_seconds()
        
        # 결과 메시지
        result_text = f"""
🔄 <b>강제 동기화 완료</b>
⏱️ 소요시간: {sync_duration:.2f}초

<b>📊 동기화 결과:</b>
- 새로운 수동 포지션: {len(sync_report.get('new_manual', []))}개
- 포지션 변경: {len(sync_report.get('size_changed', []))}개  
- 청산된 포지션: {len(sync_report.get('closed', []))}개
- 활성 포지션: {len(sync_report.get('active', []))}개
"""
        
        # 상세 정보 추가
        if sync_report.get('new_manual'):
            result_text += "\n<b>🆕 새로운 수동 포지션:</b>\n"
            for symbol in sync_report['new_manual']:
                result_text += f"• {symbol}\n"
        
        if sync_report.get('size_changed'):
            result_text += "\n<b>📏 포지션 변경:</b>\n"
            for change in sync_report['size_changed']:
                result_text += f"• {change['symbol']}: {change['change_ratio']*100:+.1f}%\n"
        
        if sync_report.get('errors'):
            result_text += f"\n⚠️ <b>오류:</b> {len(sync_report['errors'])}개"
        
        result_text += "\n<i>💡 수동 거래 감지 시 이 명령어로 즉시 동기화하세요</i>"
        
        await sync_msg.edit_text(result_text, parse_mode='HTML')
    
    async def cmd_stop_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """봇 일시 정지"""
        if not self._check_auth(update):
            return
        
        self.trading_system.stop_bot()
        await update.message.reply_text("⏸️ 봇이 일시 정지되었습니다")
    
    async def cmd_resume_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """봇 재시작"""
        if not self._check_auth(update):
            return
        
        self.trading_system.resume_bot()
        await update.message.reply_text("▶️ 봇이 재시작되었습니다")
    
    async def cmd_shutdown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """시스템 종료"""
        if not self._check_auth(update):
            return
        
        await update.message.reply_text("🛑 시스템을 종료합니다...")
        
        # 종료 신호
        self.trading_system.running = False
        if hasattr(self.trading_system, '_shutdown_event'):
            self.trading_system._shutdown_event.set()
    
    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """심볼 일시정지"""
        if not self._check_auth(update):
            return
        
        args = context.args
        if not args:
            await update.message.reply_text(
                "사용법: /pause BTCUSDT\n"
                "특정 심볼의 자동 거래를 일시정지합니다."
            )
            return
        
        symbol = args[0].upper()
        
        if hasattr(self.trading_system, 'resume_manager') and self.trading_system.resume_manager:
            await self.trading_system.resume_manager.pause_symbol(symbol, "사용자 명령")
            await update.message.reply_text(f"✅ {symbol} 일시정지 완료")
        else:
            await update.message.reply_text("❌ 스마트 재개 관리자가 활성화되지 않았습니다")
    
    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """심볼 재개"""
        if not self._check_auth(update):
            return
        
        args = context.args
        if not args:
            await update.message.reply_text(
                "사용법: /resume BTCUSDT\n"
                "일시정지된 심볼의 자동 거래를 재개합니다."
            )
            return
        
        symbol = args[0].upper()
        
        if hasattr(self.trading_system, 'resume_manager') and self.trading_system.resume_manager:
            success = await self.trading_system.resume_manager.resume_symbol(symbol, auto=False)
            if success:
                await update.message.reply_text(f"✅ {symbol} 재개 완료")
            else:
                await update.message.reply_text(f"❌ {symbol}은 일시정지 상태가 아닙니다")
        else:
            await update.message.reply_text("❌ 스마트 재개 관리자가 활성화되지 않았습니다")
    
    async def cmd_paused(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """일시정지 목록"""
        if not self._check_auth(update):
            return
        
        if hasattr(self.trading_system, 'resume_manager') and self.trading_system.resume_manager:
            status = self.trading_system.resume_manager.get_status()
            
            if not status['paused_symbols']:
                await update.message.reply_text("✅ 모든 심볼이 정상 거래 중입니다")
                return
            
            message = "⏸️ <b>일시정지된 심볼</b>\n\n"
            
            for item in status['paused_symbols']:
                message += f"<b>{item['symbol']}</b>\n"
                message += f"├ 사유: {item['reason']}\n"
                message += f"├ 경과: {item['elapsed_minutes']:.1f}분\n"
                message += f"└ 자동재개: {item['resume_estimate']}\n\n"
            
            await update.message.reply_text(message, parse_mode='HTML')
        else:
            await update.message.reply_text("❌ 스마트 재개 관리자가 활성화되지 않았습니다")
    
    async def cmd_continue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """안전 체크 - 계속"""
        if not self._check_auth(update):
            return
        
        if hasattr(self.trading_system, 'safety_checker') and self.trading_system.safety_checker:
            success = await self.trading_system.safety_checker.handle_user_decision('continue')
            if success:
                await update.message.reply_text("✅ 정상 거래를 계속합니다")
            else:
                await update.message.reply_text("❌ 안전 체크 대기 중이 아닙니다")
        else:
            await update.message.reply_text("❌ 안전 체크 관리자가 활성화되지 않았습니다")
    
    async def cmd_close_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """모든 포지션 청산"""
        if not self._check_auth(update):
            return
        
        if hasattr(self.trading_system, 'safety_checker') and self.trading_system.safety_checker:
            success = await self.trading_system.safety_checker.handle_user_decision('close_all')
            if success:
                await update.message.reply_text("🔴 모든 시스템 포지션을 청산합니다")
            else:
                await update.message.reply_text("❌ 안전 체크 대기 중이 아닙니다")
        else:
            await update.message.reply_text("❌ 안전 체크 관리자가 활성화되지 않았습니다")
    
    async def cmd_resume_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """전체 시스템 재개"""
        if not self._check_auth(update):
            return
        
        # 전략 재개
        self.trading_system.resume_bot()
        
        # 안전 모드 해제
        if hasattr(self.trading_system, 'safety_checker'):
            self.trading_system.safety_checker.safe_mode = False
        
        # 상태 저장
        if hasattr(self.trading_system, 'state_manager'):
            await self.trading_system.state_manager.save_system_state({
                'strategies_paused': False,
                'resumed_at': datetime.now().isoformat()
            })
        
        await update.message.reply_text(
            "▶️ <b>전체 시스템 재개</b>\n\n"
            "• 모든 전략 활성화\n"
            "• 안전 모드 해제\n"
            "• 정상 거래 모드",
            parse_mode='HTML'
        )
    
    async def cmd_events(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """이벤트 요약 확인"""
        if not self._check_auth(update):
            return
        
        if not EVENT_LOGGER_AVAILABLE:
            await update.message.reply_text("❌ 이벤트 로거가 활성화되지 않았습니다")
            return
        
        event_msg = await update.message.reply_text("📊 이벤트 요약 생성 중...")
        
        try:
            event_logger = get_event_logger()
            summary = await event_logger.get_event_summary()
            
            # 메시지 생성
            message = f"""
📊 <b>이벤트 요약</b>
🕒 현재: {datetime.now().strftime('%H:%M:%S')}

<b>📋 전체 이벤트:</b> {summary['total_events']}개

<b>📑 타입별 분포:</b>
"""
            
            # 타입별 통계
            for event_type, count in sorted(summary['by_type'].items(), key=lambda x: x[1], reverse=True)[:10]:
                message += f"• {event_type}: {count}개\n"
            
            # 심각도별 통계
            message += "\n<b>🌈 심각도별:</b>\n"
            for severity, count in summary['by_severity'].items():
                emoji = {
                    'INFO': 'ℹ️',
                    'WARNING': '⚠️',
                    'ERROR': '❌',
                    'CRITICAL': '🔴'
                }.get(severity, '•')
                message += f"{emoji} {severity}: {count}개\n"
            
            # 최근 에러
            if summary['recent_errors']:
                message += "\n<b>😨 최근 에러:</b>\n"
                for error in summary['recent_errors']:
                    time_str = error['timestamp'].split('T')[1].split('.')[0]
                    message += f"• [{time_str}] {error['type']}\n"
                    if error.get('message'):
                        message += f"  {error['message'][:50]}...\n"
            
            message += "\n<i>🔍 /events 명령어로 언제든지 확인하세요</i>"
            
            await event_msg.edit_text(message, parse_mode='HTML')
            
        except Exception as e:
            await event_msg.edit_text(f"❌ 이벤트 요약 조회 실패: {e}")
    
    async def cmd_sync_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """포지션 동기화 상태"""
        if not self._check_auth(update):
            return
        
        sync_msg = await update.message.reply_text("🔄 동기화 상태 확인 중...")
        
        try:
            # PositionSyncMonitor 상태 확인
            if hasattr(self.trading_system, 'sync_monitor') and self.trading_system.sync_monitor:
                status_report = self.trading_system.sync_monitor.get_status_report()
                
                message = f"""
🔄 <b>포지션 동기화 상태</b>
🕒 현재: {datetime.now().strftime('%H:%M:%S')}

{status_report}

<i>🔍 포지션 불일치 발견 시 자동 알림</i>
"""
            else:
                message = "❌ 포지션 동기화 모니터가 활성화되지 않았습니다"
            
            await sync_msg.edit_text(message, parse_mode='HTML')
            
        except Exception as e:
            await sync_msg.edit_text(f"❌ 동기화 상태 조회 실패: {e}")
    
    async def cmd_phase2_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Phase 2 컴포넌트 상태"""
        if not self._check_auth(update):
            return
        
        status_msg = await update.message.reply_text("🔍 Phase 2 상태 확인 중...")
        
        try:
            # Phase 2 Integration 체크
            if hasattr(self.trading_system, 'phase2_integration') and self.trading_system.phase2_integration:
                status = self.trading_system.phase2_integration.get_status()
                
                message = f"""
🚀 <b>Phase 2 컴포넌트 상태</b>
🕒 업데이트: {datetime.now().strftime('%H:%M:%S')}

<b>📡 초기화 상태:</b> {'✅ 완료' if status['initialized'] else '❌ 미완료'}
"""
                
                # Event Bus 상태
                if status['components']['event_bus']:
                    eb_stats = status['components']['event_bus']
                    message += f"""

<b>📨 Event Bus:</b>
├ 발행된 이벤트: {eb_stats['events_published']}개
├ 처리된 이벤트: {eb_stats['events_processed']}개
├ 실패한 이벤트: {eb_stats['events_failed']}개
├ 활성 핸들러: {eb_stats['active_handlers']}개
└ 평균 처리시간: {eb_stats['avg_processing_time_ms']:.2f}ms
"""
                
                # State Machine 상태
                if status['components']['state_machine']:
                    sm_stats = status['components']['state_machine']
                    message += f"""

<b>🎯 State Machine:</b>
├ 총 포지션: {sm_stats['total_positions']}개
├ 활성 포지션: {sm_stats['active_positions']}개
├ 종료 포지션: {sm_stats['terminal_positions']}개
└ 총 상태 전환: {sm_stats['total_transitions']}회
"""
                    
                    # 상태 분포
                    if sm_stats['state_distribution']:
                        message += "\n<b>상태 분포:</b>\n"
                        for state, count in sm_stats['state_distribution'].items():
                            message += f"• {state}: {count}개\n"
                
                # Reconciliation Engine 상태
                if status['components']['reconciliation_engine']:
                    re_stats = status['components']['reconciliation_engine']
                    engine_stats = re_stats.get('engine_stats', {})
                    message += f"""

<b>🔄 Reconciliation Engine:</b>
├ 총 검사: {engine_stats.get('total_checks', 0)}회
├ 발견된 불일치: {engine_stats.get('total_discrepancies', 0)}개
├ 자동 해결: {engine_stats.get('auto_resolutions', 0)}개
├ 수동 개입: {engine_stats.get('manual_interventions', 0)}개
└ 해결 성공률: {re_stats.get('resolution_success_rate', 0):.1f}%
"""
                
                message += "\n<i>💡 Phase 2는 이벤트 기반 아키텍처를 제공합니다</i>"
            else:
                message = "❌ Phase 2 컴포넌트가 초기화되지 않았습니다"
            
            await status_msg.edit_text(message, parse_mode='HTML')
            
        except Exception as e:
            await status_msg.edit_text(f"❌ Phase 2 상태 조회 실패: {e}")
    
    async def cmd_reconcile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """정합성 확인 실행"""
        if not self._check_auth(update):
            return
        
        # 인자 파싱
        args = context.args
        symbol = args[0].upper() if args else None
        
        recon_msg = await update.message.reply_text(
            f"🔄 정합성 확인 시작{'(' + symbol + ')' if symbol else '(전체)'}..."
        )
        
        try:
            if hasattr(self.trading_system, 'phase2_integration') and self.trading_system.phase2_integration:
                # 정합성 확인 실행
                result = await self.trading_system.phase2_integration.force_reconciliation(symbol)
                
                if result:
                    message = f"""
🔄 <b>정합성 확인 완료</b>
🕒 소요시간: {(result.completed_at - result.started_at).total_seconds():.2f}초

<b>📊 결과:</b>
├ 확인된 포지션: {result.total_positions_checked}개
├ 발견된 불일치: {len(result.discrepancies_found)}개
├ 해결 시도: {result.resolutions_attempted}개
└ 해결 성공: {result.resolutions_succeeded}개
"""
                    
                    # 주요 불일치 표시
                    if result.discrepancies_found:
                        message += "\n<b>🔍 발견된 불일치:</b>\n"
                        for disc in result.discrepancies_found[:5]:  # 최대 5개
                            message += f"• {disc.symbol}: {disc.discrepancy_type.value}\n"
                        
                        if len(result.discrepancies_found) > 5:
                            message += f"... 외 {len(result.discrepancies_found) - 5}개\n"
                    
                    # 에러가 있으면 표시
                    if result.errors:
                        message += f"\n⚠️ 오류: {len(result.errors)}개 발생"
                    
                    message += "\n<i>💡 정합성 확인은 5분마다 자동 실행됩니다</i>"
                else:
                    message = "❌ 정합성 확인 결과를 받지 못했습니다"
            else:
                message = "❌ Reconciliation Engine이 초기화되지 않았습니다"
            
            await recon_msg.edit_text(message, parse_mode='HTML')
            
        except Exception as e:
            await recon_msg.edit_text(f"❌ 정합성 확인 실패: {e}")
    
    async def cmd_position_states(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """포지션 상태 머신 조회"""
        if not self._check_auth(update):
            return
        
        states_msg = await update.message.reply_text("🎯 포지션 상태 조회 중...")
        
        try:
            if hasattr(self.trading_system, 'phase2_integration') and self.trading_system.phase2_integration:
                state_machine = self.trading_system.phase2_integration.state_machine
                
                if state_machine:
                    # 활성 포지션 상태 조회
                    active_positions = self.trading_system.position_manager.get_active_positions()
                    
                    message = f"""
🎯 <b>포지션 상태 머신</b>
🕒 현재: {datetime.now().strftime('%H:%M:%S')}

<b>📊 포지션별 상태:</b>
"""
                    
                    if active_positions:
                        for pos in active_positions:
                            state_context = state_machine.get_context(pos.position_id)
                            if state_context:
                                # 상태 이모지
                                state_emoji = {
                                    'PENDING': '⏳',
                                    'OPENING': '🔄',
                                    'ACTIVE': '✅',
                                    'MODIFYING': '📝',
                                    'CLOSING': '🔄',
                                    'CLOSED': '❌',
                                    'FAILED': '⚠️',
                                    'PAUSED': '⏸️',
                                    'MODIFIED': '📝',
                                    'RECONCILING': '🔍'
                                }.get(state_context.current_state.value, '❓')
                                
                                message += f"""

{state_emoji} <b>{pos.symbol}</b>
├ 상태: {state_context.current_state.value}
├ 이전 상태: {state_context.previous_state.value if state_context.previous_state else 'N/A'}
├ 전환 횟수: {len(state_context.state_history)}회
└ 업데이트: {state_context.updated_at.strftime('%H:%M:%S')}
"""
                                
                                # 현재 상태 지속 시간
                                duration = state_context.get_state_duration(state_context.current_state)
                                if duration:
                                    minutes = duration.total_seconds() / 60
                                    message += f"   지속시간: {minutes:.1f}분\n"
                    else:
                        message += "\n활성 포지션이 없습니다."
                    
                    # 전체 통계
                    summary = state_machine.get_state_summary()
                    message += f"""

<b>📈 전체 통계:</b>
├ 실패한 전환: {summary['failed_transitions']}회
└ 성공률: {((summary['total_transitions'] - summary['failed_transitions']) / summary['total_transitions'] * 100) if summary['total_transitions'] > 0 else 0:.1f}%
"""
                    
                    message += "\n<i>💡 포지션 상태는 자동으로 관리됩니다</i>"
                else:
                    message = "❌ State Machine이 초기화되지 않았습니다"
            else:
                message = "❌ Phase 2 컴포넌트가 초기화되지 않았습니다"
            
            await states_msg.edit_text(message, parse_mode='HTML')
            
        except Exception as e:
            await states_msg.edit_text(f"❌ 상태 조회 실패: {e}")
    
    async def cmd_discrepancies(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """불일치 이력 조회"""
        if not self._check_auth(update):
            return
        
        # 인자 파싱
        args = context.args
        symbol = args[0].upper() if args else None
        limit = int(args[1]) if len(args) > 1 else 20
        
        disc_msg = await update.message.reply_text(
            f"🔍 불일치 이력 조회 중{'(' + symbol + ')' if symbol else ''}..."
        )
        
        try:
            if hasattr(self.trading_system, 'phase2_integration') and self.trading_system.phase2_integration:
                # 불일치 이력 조회
                history = self.trading_system.phase2_integration.get_discrepancy_history(symbol, limit)
                
                if history:
                    message = f"""
🔍 <b>불일치 이력</b>
🕒 현재: {datetime.now().strftime('%H:%M:%S')}
{'🎯 심볼: ' + symbol if symbol else '📊 전체'}

<b>최근 {len(history)}개 불일치:</b>
"""
                    
                    # 타입별 이모지
                    type_emoji = {
                        'POSITION_NOT_IN_SYSTEM': '🆕',
                        'POSITION_NOT_IN_EXCHANGE': '❌',
                        'SIZE_MISMATCH': '📏',
                        'PRICE_MISMATCH': '💰',
                        'LEVERAGE_MISMATCH': '⚖️',
                        'SIDE_MISMATCH': '🔄',
                        'STATE_MISMATCH': '🎯'
                    }
                    
                    # 불일치 표시
                    for disc in history[:10]:  # 최대 10개 표시
                        emoji = type_emoji.get(disc['type'], '❓')
                        time_str = disc['detected_at'].split('T')[1].split('.')[0]
                        
                        message += f"""

{emoji} <b>{disc['symbol']}</b> [{time_str}]
├ 타입: {disc['type']}
├ 심각도: {disc['severity']}
"""
                        
                        # SIZE_MISMATCH인 경우 상세 정보
                        if disc['type'] == 'SIZE_MISMATCH' and disc.get('details'):
                            details = disc['details']
                            message += f"├ 시스템: {details.get('system_size', 'N/A'):.4f}\n"
                            message += f"├ 거래소: {details.get('exchange_size', 'N/A'):.4f}\n"
                            message += f"└ 차이: {details.get('difference_pct', 0):.1f}%\n"
                        else:
                            message += f"└ {'시스템에만 존재' if disc['type'] == 'POSITION_NOT_IN_EXCHANGE' else '거래소에만 존재' if disc['type'] == 'POSITION_NOT_IN_SYSTEM' else '정보 불일치'}\n"
                    
                    if len(history) > 10:
                        message += f"\n... 외 {len(history) - 10}개"
                    
                    # 타입별 통계
                    type_counts = {}
                    for disc in history:
                        disc_type = disc['type']
                        type_counts[disc_type] = type_counts.get(disc_type, 0) + 1
                    
                    if type_counts:
                        message += "\n\n<b>📊 타입별 통계:</b>\n"
                        for disc_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
                            emoji = type_emoji.get(disc_type, '❓')
                            message += f"{emoji} {disc_type}: {count}개\n"
                    
                    message += "\n<i>💡 불일치는 자동으로 해결을 시도합니다</i>"
                else:
                    message = "📊 최근 불일치 이력이 없습니다"
            else:
                message = "❌ Phase 2 컴포넌트가 초기화되지 않았습니다"
            
            await disc_msg.edit_text(message, parse_mode='HTML')
            
        except Exception as e:
            await disc_msg.edit_text(f"❌ 불일치 이력 조회 실패: {e}")
    
    async def cmd_manual_trade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """수동 거래 등록"""
        if not self._check_auth(update):
            return
        
        try:
            # Hybrid Trading Manager import 및 생성
            from src.core.hybrid_trading_manager import HybridTradingManager
            
            # 명령어 파싱
            args = context.args
            if len(args) < 2:
                await update.message.reply_text(
                    "❌ 잘못된 형식입니다.\n\n"
                    "<b>사용법:</b>\n"
                    "/manual BTCUSDT long [size] [leverage]\n"
                    "/manual BTCUSDT short [size] [leverage]\n\n"
                    "<b>예시:</b>\n"
                    "/manual BTCUSDT long - 기본 설정으로 롱\n"
                    "/manual BTCUSDT short 0.01 - 0.01 BTC 숏\n"
                    "/manual BTCUSDT long 0.02 10 - 0.02 BTC, 10x 레버리지\n\n"
                    "기본값: 계좌의 24%, 15x 레버리지",
                    parse_mode='HTML'
                )
                return
            
            symbol = args[0].upper()
            side = args[1].lower()
            
            if side not in ['long', 'short']:
                await update.message.reply_text("❌ side는 'long' 또는 'short'여야 합니다.")
                return
            
            # 옵션 파싱
            size = float(args[2]) if len(args) > 2 else None
            leverage = int(args[3]) if len(args) > 3 else None
            
            # 메모 추가 (마지막 인자들을 합침)
            comment = ' '.join(args[4:]) if len(args) > 4 else "텔레그램 수동 거래"
            
            # Hybrid Trading Manager 가져오기 (또는 생성)
            if not hasattr(self.trading_system, 'hybrid_manager'):
                self.trading_system.hybrid_manager = HybridTradingManager(
                    self.trading_system.position_manager,
                    self.trading_system.binance_api,
                    self.trading_system.notification_manager
                )
            
            # 수동 거래 등록
            loading_msg = await update.message.reply_text("🔄 수동 거래 등록 중...")
            
            success, message = await self.trading_system.hybrid_manager.register_manual_trade(
                symbol=symbol,
                side=side,
                size=size,
                leverage=leverage,
                comment=comment
            )
            
            if success:
                await loading_msg.edit_text(f"✅ {message}")
            else:
                await loading_msg.edit_text(f"❌ {message}")
        
        except ValueError as e:
            await update.message.reply_text(f"❌ 잘못된 값: {str(e)}")
        except Exception as e:
            logger.error(f"수동 거래 명령 처리 실패: {e}")
            await update.message.reply_text(f"❌ 오류 발생: {str(e)}")
    
    async def cmd_close_manual(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """수동 거래 청산"""
        if not self._check_auth(update):
            return
        
        try:
            args = context.args
            if not args:
                await update.message.reply_text(
                    "❌ 심볼을 지정하세요.\n\n"
                    "<b>사용법:</b>\n"
                    "/close_manual BTCUSDT [percentage]\n\n"
                    "<b>예시:</b>\n"
                    "/close_manual BTCUSDT - 전체 청산\n"
                    "/close_manual BTCUSDT 50 - 50% 부분 청산\n"
                    "/close_manual BTCUSDT 100 익절 - 전체 청산 (익절)",
                    parse_mode='HTML'
                )
                return
            
            symbol = args[0].upper()
            
            # 퍼센트 파싱
            percentage = 100.0
            comment_start_idx = 1
            
            if len(args) > 1 and args[1].replace('.', '').isdigit():
                percentage = float(args[1])
                comment_start_idx = 2
                
                if percentage <= 0 or percentage > 100:
                    await update.message.reply_text("❌ 청산 비율은 0-100 사이여야 합니다.")
                    return
            
            # 청산 사유
            comment = ' '.join(args[comment_start_idx:]) if len(args) > comment_start_idx else "텔레그램 수동 청산"
            
            # Hybrid Manager 확인
            if not hasattr(self.trading_system, 'hybrid_manager'):
                # 수동 포지션이 있는지 먼저 확인
                position = self.trading_system.position_manager.get_position(symbol)
                if position and position.is_manual:
                    # 직접 청산
                    success = await self.trading_system.position_manager.close_position(
                        symbol, comment, force=True
                    )
                    if success:
                        await update.message.reply_text(f"✅ {symbol} 수동 포지션 청산 완료")
                    else:
                        await update.message.reply_text(f"❌ {symbol} 청산 실패")
                else:
                    await update.message.reply_text(f"❌ {symbol}에 수동 포지션이 없습니다.")
                return
            
            # 청산 실행
            loading_msg = await update.message.reply_text(
                f"🔄 {symbol} 청산 중... ({percentage:.0f}%)"
            )
            
            success, message = await self.trading_system.hybrid_manager.close_manual_trade(
                symbol, percentage, comment
            )
            
            if success:
                await loading_msg.edit_text(f"✅ {message}")
            else:
                await loading_msg.edit_text(f"❌ {message}")
        
        except Exception as e:
            logger.error(f"수동 청산 명령 처리 실패: {e}")
            await update.message.reply_text(f"❌ 오류 발생: {str(e)}")
    
    async def cmd_manual_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """수동 포지션 목록 조회"""
        if not self._check_auth(update):
            return
        
        try:
            # 수동 포지션만 필터링
            positions = self.trading_system.position_manager.get_active_positions()
            manual_positions = [p for p in positions if p.is_manual]
            
            if not manual_positions:
                await update.message.reply_text("ℹ️ 활성화된 수동 포지션이 없습니다.")
                return
            
            # 메시지 생성
            message = "🔵 <b>수동 포지션 목록</b>\n\n"
            
            total_positions = 0
            for pos in manual_positions:
                total_positions += 1
                
                # 현재가 조회
                current_price = await self.trading_system.binance_api.get_current_price(pos.symbol)
                
                # 손익 계산
                pnl_percent = 0
                pnl_usdt = 0
                if current_price and pos.entry_price:
                    if pos.side.upper() == 'LONG':
                        pnl_percent = (current_price - pos.entry_price) / pos.entry_price * 100
                    else:
                        pnl_percent = (pos.entry_price - current_price) / pos.entry_price * 100
                    pnl_percent *= pos.leverage
                    pnl_usdt = pos.size * current_price * (pnl_percent / 100) / pos.leverage
                
                # 포지션 정보
                message += f"<b>{pos.symbol}</b> {pos.side}\n"
                message += f"├ 수량: {pos.size:.4f}\n"
                message += f"├ 진입가: ${pos.entry_price:.2f}\n"
                message += f"├ 현재가: ${current_price:.2f}\n" if current_price else "├ 현재가: N/A\n"
                message += f"├ 손익: {pnl_percent:+.2f}% (${pnl_usdt:+.2f})\n"
                message += f"├ 레버리지: {pos.leverage}x\n"
                
                # 보유 시간 계산
                if hasattr(pos, 'created_at'):
                    try:
                        # created_at은 문자열이므로 변환 필요
                        created_time = datetime.fromisoformat(pos.created_at)
                        holding_time = datetime.now() - created_time
                        hours = int(holding_time.total_seconds() // 3600)
                        minutes = int((holding_time.total_seconds() % 3600) // 60)
                        message += f"└ 보유시간: {hours}시간 {minutes}분\n"
                    except Exception as e:
                        logger.error(f"보유시간 계산 실패: {e}")
                        message += f"└ 전략: {pos.strategy_name or 'MANUAL'}\n"
                else:
                    message += f"└ 전략: {pos.strategy_name or 'MANUAL'}\n"
                
                message += "\n"
            
            # Hybrid Manager 통계 추가 (있는 경우)
            if hasattr(self.trading_system, 'hybrid_manager'):
                manual_trades = self.trading_system.hybrid_manager.manual_trades
                message += f"\n<b>📊 통계:</b>\n"
                message += f"• 활성 수동 포지션: {total_positions}개\n"
                message += f"• 관리 중인 심볼: {len(manual_trades)}개\n"
                
                # 레버리지 오버라이드 정보
                overrides = self.trading_system.hybrid_manager.manual_leverage_override
                if overrides:
                    message += f"\n<b>⚙️ 커스텀 레버리지:</b>\n"
                    for symbol, leverage in overrides.items():
                        message += f"• {symbol}: {leverage}x\n"
            
            message += "\n<i>💡 수동 포지션은 자동 청산되지 않습니다</i>"
            
            await update.message.reply_text(message, parse_mode='HTML')
        
        except Exception as e:
            logger.error(f"수동 포지션 조회 실패: {e}")
            await update.message.reply_text(f"❌ 오류 발생: {str(e)}")
    
    async def cmd_modify_manual(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """수동 거래 수정 (피라미딩)"""
        if not self._check_auth(update):
            return
        
        try:
            args = context.args
            if len(args) < 2:
                await update.message.reply_text(
                    "❌ 잘못된 형식입니다.\n\n"
                    "<b>사용법:</b>\n"
                    "/modify_manual BTCUSDT add 0.01 - 0.01 BTC 추가\n"
                    "/modify_manual BTCUSDT leverage 20 - 레버리지 변경\n\n"
                    "<b>참고:</b>\n"
                    "• 피라미딩: 같은 방향으로 포지션 추가\n"
                    "• 레버리지: 다음 거래부터 적용\n"
                    "• 손절/익절: 거래소에서 직접 설정",
                    parse_mode='HTML'
                )
                return
            
            symbol = args[0].upper()
            action = args[1].lower()
            
            # 포지션 확인
            position = self.trading_system.position_manager.get_position(symbol)
            if not position or position.status != 'ACTIVE':
                await update.message.reply_text(f"❌ {symbol}에 활성 포지션이 없습니다.")
                return
            
            if not position.is_manual:
                await update.message.reply_text(f"❌ {symbol}은 시스템 자동 포지션입니다.")
                return
            
            # Hybrid Manager 생성 (필요시)
            from src.core.hybrid_trading_manager import HybridTradingManager
            if not hasattr(self.trading_system, 'hybrid_manager'):
                self.trading_system.hybrid_manager = HybridTradingManager(
                    self.trading_system.position_manager,
                    self.trading_system.binance_api,
                    self.trading_system.notification_manager
                )
            
            loading_msg = await update.message.reply_text(f"🔄 {symbol} 포지션 수정 중...")
            
            if action == 'add' and len(args) > 2:
                # 피라미딩
                add_size = float(args[2])
                success, message = await self.trading_system.hybrid_manager.modify_manual_trade(
                    symbol=symbol,
                    add_size=add_size
                )
            elif action == 'leverage' and len(args) > 2:
                # 레버리지 변경
                new_leverage = int(args[2])
                if new_leverage < 1 or new_leverage > 125:
                    await loading_msg.edit_text("❌ 레버리지는 1-125 사이여야 합니다.")
                    return
                    
                success, message = await self.trading_system.hybrid_manager.modify_manual_trade(
                    symbol=symbol,
                    new_leverage=new_leverage
                )
            else:
                await loading_msg.edit_text("❌ 잘못된 액션입니다. 'add' 또는 'leverage'를 사용하세요.")
                return
            
            if success:
                await loading_msg.edit_text(f"✅ {message}")
            else:
                await loading_msg.edit_text(f"❌ {message}")
        
        except ValueError as e:
            await update.message.reply_text(f"❌ 잘못된 값: {str(e)}")
        except Exception as e:
            logger.error(f"수동 거래 수정 실패: {e}")
            await update.message.reply_text(f"❌ 오류 발생: {str(e)}")
    
    async def cmd_strategies(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """전략 목록 및 상태"""
        if not self._check_auth(update):
            return
        
        try:
            if not hasattr(self.trading_system, 'strategies') or not self.trading_system.strategies:
                await update.message.reply_text("ℹ️ 활성화된 전략이 없습니다.")
                return
            
            message = "🧠 <b>전략 목록 및 상태</b>\n\n"
            
            # 멀티계좌 상태 확인
            multi_account_enabled = False
            account_strategies = {}  # {account_name: [strategies]}
            
            if hasattr(self.trading_system, 'multi_account_manager'):
                multi_account_manager = self.trading_system.multi_account_manager
                if multi_account_manager and multi_account_manager.is_multi_account_enabled():
                    multi_account_enabled = True
                    message += "🎯 <b>멀티계좌 모드 활성</b>\n\n"
            
            # 전략별 상태 표시
            for i, strategy in enumerate(self.trading_system.strategies, 1):
                strategy_name = getattr(strategy, 'name', 'Unknown')
                
                # 상태 확인
                if hasattr(strategy, 'is_paused'):
                    status = '⏸️ 일시정지' if strategy.is_paused else '▶️ 실행중'
                else:
                    status = '▶️ 실행중'
                
                message += f"<b>{i}. {strategy_name} - {status}</b>\n"
                
                # 계좌 정보 표시 (멀티계좌 모드인 경우)
                account_name = getattr(strategy, 'account_name', 'MAIN')
                message += f"   계좌: {account_name}\n"
                
                # 계좌별 전략 그룹핑
                if account_name not in account_strategies:
                    account_strategies[account_name] = []
                account_strategies[account_name].append(strategy_name)
                
                # 포지션 정보
                if hasattr(self.trading_system.position_manager, 'get_positions_by_strategy'):
                    positions = self.trading_system.position_manager.get_positions_by_strategy(strategy_name)
                    active_positions = [p for p in positions if p.status == 'ACTIVE']
                    message += f"   활성 포지션: {len(active_positions)}개\n"
                
                # 전략 설정 정보
                if hasattr(strategy, 'config'):
                    message += f"   레버리지: {strategy.config.get('leverage', 'N/A')}x\n"
                    message += f"   포지션 크기: {strategy.config.get('position_size', 'N/A')}%\n"
                
                message += "\n"
            
            # 멀티계좌 요약 정보
            if multi_account_enabled and account_strategies:
                message += "<b>💼 계좌별 전략 요약</b>\n"
                for account, strategies in account_strategies.items():
                    message += f"• {account}: {', '.join(strategies)}\n"
                message += "\n"
            
            message += "<i>💡 전략 상태를 변경하려면:\n"
            message += "/pause_strategy [전략명]\n"
            message += "/resume_strategy [전략명]\n"
            if multi_account_enabled:
                message += "/accounts - 계좌별 상태 확인</i>"
            else:
                message += "</i>"
            
            await update.message.reply_text(message, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"전략 목록 조회 실패: {e}")
            await update.message.reply_text(f"❌ 오류 발생: {str(e)}")
    
    async def cmd_pause_strategy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """특정 전략 일시정지"""
        if not self._check_auth(update):
            return
        
        args = context.args
        if not args:
            await update.message.reply_text(
                "사용법: /pause_strategy [전략명]\n"
                "예: /pause_strategy TFPE"
            )
            return
        
        strategy_name = args[0].upper()
        
        try:
            # 전략 찾기
            target_strategy = None
            for strategy in self.trading_system.strategies:
                if getattr(strategy, 'name', '').upper() == strategy_name:
                    target_strategy = strategy
                    break
            
            if not target_strategy:
                await update.message.reply_text(f"❌ {strategy_name} 전략을 찾을 수 없습니다.")
                return
            
            # 일시정지
            if hasattr(target_strategy, 'pause'):
                await target_strategy.pause()
                await update.message.reply_text(f"⏸️ {strategy_name} 전략이 일시정지되었습니다.")
            else:
                # pause 메서드가 없으면 is_paused 플래그만 설정
                target_strategy.is_paused = True
                await update.message.reply_text(f"⏸️ {strategy_name} 전략이 일시정지되었습니다.")
            
        except Exception as e:
            logger.error(f"전략 일시정지 실패: {e}")
            await update.message.reply_text(f"❌ 오류 발생: {str(e)}")
    
    async def cmd_resume_strategy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """특정 전략 재개"""
        if not self._check_auth(update):
            return
        
        args = context.args
        if not args:
            await update.message.reply_text(
                "사용법: /resume_strategy [전략명]\n"
                "예: /resume_strategy TFPE"
            )
            return
        
        strategy_name = args[0].upper()
        
        try:
            # 전략 찾기
            target_strategy = None
            for strategy in self.trading_system.strategies:
                if getattr(strategy, 'name', '').upper() == strategy_name:
                    target_strategy = strategy
                    break
            
            if not target_strategy:
                await update.message.reply_text(f"❌ {strategy_name} 전략을 찾을 수 없습니다.")
                return
            
            # 재개
            if hasattr(target_strategy, 'resume'):
                await target_strategy.resume()
                await update.message.reply_text(f"▶️ {strategy_name} 전략이 재개되었습니다.")
            else:
                # resume 메서드가 없으면 is_paused 플래그만 해제
                target_strategy.is_paused = False
                await update.message.reply_text(f"▶️ {strategy_name} 전략이 재개되었습니다.")
            
        except Exception as e:
            logger.error(f"전략 재개 실패: {e}")
            await update.message.reply_text(f"❌ 오류 발생: {str(e)}")
    
    async def cmd_strategy_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """전략별 상세 상태"""
        if not self._check_auth(update):
            return
        
        args = context.args
        if not args:
            await update.message.reply_text(
                "사용법: /strategy_status [전략명]\n"
                "예: /strategy_status TFPE"
            )
            return
        
        strategy_name = args[0].upper()
        
        try:
            # 전략 찾기
            target_strategy = None
            for strategy in self.trading_system.strategies:
                if getattr(strategy, 'name', '').upper() == strategy_name:
                    target_strategy = strategy
                    break
            
            if not target_strategy:
                await update.message.reply_text(f"❌ {strategy_name} 전략을 찾을 수 없습니다.")
                return
            
            # 상태 수집
            message = f"🔍 <b>{strategy_name} 전략 상세 상태</b>\n\n"
            
            # 기본 상태
            if hasattr(target_strategy, 'is_paused'):
                status = '⏸️ 일시정지' if target_strategy.is_paused else '▶️ 실행중'
            else:
                status = '▶️ 실행중'
            
            message += f"<b>상태:</b> {status}\n"
            
            # 전략 특화 정보
            if hasattr(target_strategy, 'get_strategy_info'):
                info = target_strategy.get_strategy_info()
                for key, value in info.items():
                    if key not in ['name']:  # 이름은 제외
                        message += f"<b>{key}:</b> {value}\n"
            
            # 포지션 정보
            if hasattr(self.trading_system.position_manager, 'get_positions_by_strategy'):
                positions = self.trading_system.position_manager.get_positions_by_strategy(strategy_name)
                active_positions = [p for p in positions if p.status == 'ACTIVE']
                
                message += f"\n<b>포지션 현황:</b>\n"
                message += f"활성 포지션: {len(active_positions)}개\n"
                
                if active_positions:
                    message += "\n<b>포지션 목록:</b>\n"
                    for pos in active_positions:
                        message += f"• {pos.symbol} {pos.side} {pos.size:.4f}\n"
            
            # 성과 지표 (있는 경우)
            if hasattr(target_strategy, 'get_performance_stats'):
                stats = target_strategy.get_performance_stats()
                if stats:
                    message += "\n<b>성과 지표:</b>\n"
                    for key, value in stats.items():
                        message += f"{key}: {value}\n"
            
            await update.message.reply_text(message, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"전략 상태 조회 실패: {e}")
            await update.message.reply_text(f"❌ 오류 발생: {str(e)}")
    
    async def cmd_accounts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """계좌별 현황"""
        if not self._check_auth(update):
            return
        
        try:
            # 현재는 단일 계좌 모드인 경우
            if not hasattr(self.trading_system, 'multi_account_manager') or \
               not self.trading_system.multi_account_manager or \
               not self.trading_system.multi_account_manager.is_multi_account_enabled():
                
                # 단일 계좌 정보
                balance = await self.trading_system.binance_api.get_account_balance()
                positions = self.trading_system.position_manager.get_active_positions()
                
                message = "💼 <b>계좌 현황 (단일 계좌 모드)</b>\n\n"
                message += f"<b>마스터 계좌</b>\n"
                message += f"잔고: ${balance:.2f} USDT\n"
                message += f"포지션: {len(positions)}개\n"
                
                # 전략별 포지션
                strategy_positions = {}
                for pos in positions:
                    strategy = pos.strategy_name or 'MANUAL'
                    strategy_positions[strategy] = strategy_positions.get(strategy, 0) + 1
                
                if strategy_positions:
                    message += "\n<b>전략별 포지션:</b>\n"
                    for strategy, count in strategy_positions.items():
                        message += f"• {strategy}: {count}개\n"
                
                message += "\n<i>💡 멀티계좌 모드는 config.yaml에서 활성화할 수 있습니다</i>"
                
            else:
                # 멀티계좌 모드
                multi_manager = self.trading_system.multi_account_manager
                
                message = "🎯 <b>멀티계좌 현황</b>\n\n"
                
                # 전체 요약
                system_stats = multi_manager.get_system_stats()
                message += f"<b>📈 전체 요약</b>\n"
                message += f"총 계좌: {system_stats['accounts']['total']}개\n"
                message += f"활성 계좌: {system_stats['accounts']['active']}개\n"
                message += f"총 포지션: {system_stats['positions']}개\n\n"
                
                # 마스터 계좌
                if multi_manager.master_account:
                    master_summary = await multi_manager.get_account_summary('MASTER')
                    message += f"<b>🎆 마스터 계좌</b>\n"
                    message += f"잔고: ${master_summary.get('balance', 0):.2f}\n"
                    message += f"포지션: {len(master_summary.get('positions', []))}개\n\n"
                
                # 서브 계좌
                if multi_manager.accounts:
                    message += "<b>📂 서브 계좌</b>\n"
                    for account_id, account_info in multi_manager.accounts.items():
                        summary = await multi_manager.get_account_summary(account_id)
                        
                        # 상태 이모지
                        status_emoji = {
                            'ACTIVE': '✅',
                            'PAUSED': '⏸️',
                            'ERROR': '⚠️',
                            'DISABLED': '❌'
                        }.get(account_info.status.value, '❓')
                        
                        message += f"\n{status_emoji} <b>{account_id}</b>\n"
                        message += f"  전략: {account_info.strategy}\n"
                        message += f"  잔고: ${summary.get('balance', 0):.2f}\n"
                        message += f"  포지션: {len(summary.get('positions', []))}개\n"
                        
                        # 성과 표시 (있는 경우)
                        if account_info.performance and account_info.performance.total_trades > 0:
                            perf = account_info.performance
                            message += f"  수익률: {perf.win_rate:.1f}%\n"
                            message += f"  총 PnL: ${perf.total_pnl:.2f}\n"
                
                # 마지막 동기화 시간
                if system_stats.get('last_sync'):
                    message += f"\n<i>🔄 마지막 동기화: {system_stats['last_sync'].split('T')[1].split('.')[0]}</i>"
            
            await update.message.reply_text(message, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"계좌 현황 조회 실패: {e}")
            await update.message.reply_text(f"❌ 오류 발생: {str(e)}")
    
    async def cmd_account_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """특정 계좌 상세 상태"""
        if not self._check_auth(update):
            return
        
        args = context.args
        if not args:
            await update.message.reply_text(
                "사용법: /account_status [계좌명]\n"
                "예: /account_status MASTER\n"
                "예: /account_status sub1"
            )
            return
        
        account_id = args[0].upper() if args[0].upper() == 'MASTER' else args[0]
        
        try:
            # 멀티계좌 모드 확인
            if not hasattr(self.trading_system, 'multi_account_manager') or \
               not self.trading_system.multi_account_manager:
                await update.message.reply_text("ℹ️ 멀티계좌 모드가 활성화되지 않았습니다.")
                return
            
            multi_manager = self.trading_system.multi_account_manager
            
            # 계좌 요약 조회
            summary = await multi_manager.get_account_summary(account_id)
            
            if 'error' in summary:
                await update.message.reply_text(f"❌ {account_id} 계좌를 찾을 수 없습니다.")
                return
            
            # 상세 정보 표시
            message = f"🔍 <b>{account_id} 계좌 상세 상태</b>\n\n"
            
            # 기본 정보
            message += f"<b>📄 기본 정보</b>\n"
            message += f"상태: {summary['status']}\n"
            message += f"전략: {summary['strategy']}\n"
            message += f"잔고: ${summary['balance']:.2f} USDT\n\n"
            
            # 포지션 정보
            positions = summary.get('positions', [])
            if positions:
                message += f"<b>📈 활성 포지션 ({len(positions)}개)</b>\n"
                for pos in positions:
                    symbol = pos.get('symbol', 'N/A')
                    side = pos.get('side', 'N/A')
                    size = pos.get('size', 0)
                    entry_price = pos.get('entry_price', 0)
                    
                    message += f"\n• <b>{symbol}</b> {side}\n"
                    message += f"  수량: {size:.4f}\n"
                    message += f"  진입가: ${entry_price:.2f}\n"
            else:
                message += "<b>📈 활성 포지션</b>\n포지션 없음\n\n"
            
            # 성과 정보
            performance = summary.get('performance', {})
            if performance and performance.get('total_trades', 0) > 0:
                message += "<b>🎯 성과 지표</b>\n"
                message += f"총 거래: {performance.get('total_trades', 0)}회\n"
                message += f"승률: {performance.get('win_rate', 0):.1f}%\n"
                message += f"총 손익: ${performance.get('total_pnl', 0):.2f}\n"
                message += f"최대 DD: {performance.get('max_drawdown', 0):.1f}%\n"
            
            await update.message.reply_text(message, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"계좌 상세 조회 실패 ({account_id}): {e}")
            await update.message.reply_text(f"❌ 오류 발생: {str(e)}")
    
    async def cmd_fix_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """포지션 인식 문제 수정"""
        if not self._check_auth(update):
            return
        
        fix_msg = await update.message.reply_text("🔧 포지션 인식 문제 수정 중...")
        
        try:
            if PHASE2_FIX_AVAILABLE:
                helper = MultiAccountStatusHelper(self.trading_system)
                result = await helper.fix_position_recognition()
                
                if result['success']:
                    message = f"""
✅ <b>포지션 인식 수정 완료</b>

<b>🔧 수정 결과:</b>
• 재분류된 포지션: {result['fixed_positions']}개
• 활성 포지션: {len(result['sync_report'].get('active', []))}개
• 수동 포지션: {len(result['sync_report'].get('new_manual', []))}개

/status 명령어로 새로운 상태를 확인하세요.
"""
                else:
                    message = f"❌ 포지션 수정 실패: {result.get('error', 'Unknown error')}"
            else:
                # 기본 동기화만 수행
                sync_report = await self.trading_system.position_manager.sync_positions()
                message = f"""
🔄 <b>포지션 동기화 완료</b>

활성 포지션: {len(sync_report.get('active', []))}개
수동 포지션: {len(sync_report.get('new_manual', []))}개
"""
            
            await fix_msg.edit_text(message, parse_mode='HTML')
            
        except Exception as e:
            await fix_msg.edit_text(f"❌ 오류 발생: {str(e)}")
    
    def _format_uptime(self, uptime) -> str:
        """업타임 포맷팅"""
        if not uptime:
            return "N/A"
        
        days = uptime.days
        hours = uptime.seconds // 3600
        minutes = (uptime.seconds // 60) % 60
        
        return f"{days}일 {hours}시간 {minutes}분"
    
    async def run_polling(self):
        """폴링 실행"""
        try:
            await self.application.initialize()
            await self.application.start()
            
            logger.info("텔레그램 봇 폴링 시작")
            
            # 폴링 시작
            await self.application.updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
            
            # 실행 유지
            while self.trading_system.is_running:
                await asyncio.sleep(1)
            
            # 종료
            if self.application.updater.running:
                await self.application.updater.stop()
                
        except asyncio.CancelledError:
            logger.info("텔레그램 폴링 취소됨")
            raise
        except Exception as e:
            logger.error(f"텔레그램 폴링 오류: {e}")
    
    async def cleanup(self):
        """정리 작업"""
        try:
            if self.application:
                logger.info("텔레그램 봇 정리 중...")
                
                if self.application.updater and self.application.updater.running:
                    await self.application.updater.stop()
                
                await self.application.stop()
                await asyncio.sleep(0.5)
                await self.application.shutdown()
                
            logger.info("텔레그램 명령어 봇 정리 완료")
            
        except Exception as e:
            logger.error(f"텔레그램 봇 정리 중 오류: {e}")
    
    def get_stats(self) -> Dict:
        """통계 반환"""
        return {
            'commands_executed': self.stats['commands_executed'],
            'commands_failed': self.stats['commands_failed'],
            'last_command': self.stats['last_command'],
            'authorized_users': len(self.authorized_users)
        }


class TelegramCommandHandler:
    """레거시 호환성을 위한 래퍼 클래스"""
    
    def __init__(self, position_manager, notification_manager, trading_system):
        self.position_manager = position_manager
        self.notification_manager = notification_manager
        self.trading_system = trading_system
        self.commands = None
        
        # 봇 토큰 가져오기
        bot_token = self._get_bot_token()
        
        if bot_token:
            # TelegramCommands 인스턴스 생성
            self.commands = TelegramCommands(
                bot_token=bot_token,
                trading_system=trading_system
            )
            logger.info(f"TelegramCommands 인스턴스 생성 완료")
        else:
            logger.error("텔레그램 봇 토큰을 찾을 수 없습니다")
    
    def _get_bot_token(self) -> Optional[str]:
        """봇 토큰 가져오기 (다양한 소스에서 시도)"""
        # 1. 환경변수
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if bot_token:
            logger.info("환경변수에서 봇 토큰 발견")
            return bot_token
        
        # 2. trading_system.config
        if hasattr(self.trading_system, 'config'):
            telegram_config = self.trading_system.config.get('telegram', {})
            bot_token = telegram_config.get('bot_token')
            if bot_token:
                logger.info("config에서 봇 토큰 발견")
                return bot_token
        
        # 3. config_manager
        if hasattr(self.trading_system, 'config_manager'):
            try:
                telegram_config = self.trading_system.config_manager.get_telegram_config()
                bot_token = telegram_config.get('bot_token')
                if bot_token:
                    logger.info("config_manager에서 봇 토큰 발견")
                    return bot_token
            except:
                pass
        
        logger.error("봇 토큰을 찾을 수 없습니다. TELEGRAM_BOT_TOKEN 환경변수를 확인하세요.")
        return None
    
    async def initialize(self):
        """초기화"""
        if self.commands:
            return await self.commands.initialize()
        else:
            logger.error("TelegramCommands가 초기화되지 않았습니다")
            return False
    
    async def run_polling(self):
        """폴링 실행"""
        if self.commands:
            return await self.commands.run_polling()
        else:
            logger.error("TelegramCommands가 초기화되지 않았습니다")
            # 오류 없이 대기
            while hasattr(self.trading_system, 'is_running') and self.trading_system.is_running:
                await asyncio.sleep(60)
    
    async def cleanup(self):
        """정리 작업"""
        if self.commands:
            await self.commands.cleanup()


def setup_telegram_commands(bot, handler):
    """레거시 호환성을 위한 setup 함수"""
    logger.info("setup_telegram_commands 호출됨 (레거시 호환성)")
    pass
