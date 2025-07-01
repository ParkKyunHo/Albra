"""
AlbraTrading 웹 대시보드
확장성과 호환성을 고려한 완전한 구현
"""
from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_cors import CORS
import json
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Any, Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor
import functools
import os
from src.web.performance_dashboard import PerformanceDashboard

logger = logging.getLogger(__name__)

# Flask 로깅 레벨 조정
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.ERROR)


class DashboardApp:
    """웹 대시보드 애플리케이션"""
    
    def __init__(self, position_manager=None, binance_api=None, strategies=None, 
                 config=None, state_manager=None, notification_manager=None):
        self.app = Flask(__name__, 
                        template_folder='templates',
                        static_folder='static')
        # CORS 설정 개선 - 모든 오리진 허용
        CORS(self.app, resources={r"/api/*": {"origins": "*"}})
        
        # 시스템 컴포넌트 참조
        self.position_manager = position_manager
        self.strategies = strategies or []
        self.config = config or {}
        self.binance_api = binance_api  # exchange 대신 binance_api 사용
        self.state_manager = state_manager
        self.notification_manager = notification_manager
        self.performance_tracker = None  # 성과 추적기 추가
        
        # 메트릭 저장
        self.metrics = {
            'start_time': datetime.now(),
            'requests_count': 0,
            'errors_count': 0,
            'last_sync_time': None,
            'api_calls': 0
        }
        
        # 캐시 설정
        self.cache = {
            'positions': {'data': None, 'timestamp': None, 'ttl': 5},  # 5초
            'account': {'data': None, 'timestamp': None, 'ttl': 10},   # 10초
            'status': {'data': None, 'timestamp': None, 'ttl': 3},     # 3초
            'prices': {'data': {}, 'timestamp': None, 'ttl': 2}        # 2초 - 가격 캐시 추가
        }
        
        # 비동기 실행을 위한 스레드 풀
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # 성과 대시보드 초기화
        self.performance_dashboard = None
        
        # 라우트 설정
        self._setup_routes()
        
        logger.info("DashboardApp 초기화 완료")
    
    def _setup_routes(self):
        """라우트 설정"""
        
        @self.app.route('/')
        def index():
            """메인 대시보드 페이지"""
            self.metrics['requests_count'] += 1
            
            # 템플릿이 없으면 기본 HTML 반환
            try:
                return render_template('dashboard.html')
            except:
                return self._get_default_html()
        
        @self.app.route('/performance')
        def performance():
            """성과 분석 대시보드 페이지"""
            self.metrics['requests_count'] += 1
            
            try:
                return render_template('performance.html')
            except Exception as e:
                logger.error(f"Performance template 오류: {e}")
                return f"<h1>Performance Dashboard</h1><p>Error: {e}</p>"
        
        @self.app.route('/api/status')
        def api_status():
            """시스템 상태 API"""
            self.metrics['requests_count'] += 1
            
            try:
                # 캐시 확인
                cached = self._get_cached('status')
                if cached:
                    return jsonify(cached)
                
                status = self._build_status()
                self._set_cache('status', status)
                return jsonify(status)
                
            except Exception as e:
                self.metrics['errors_count'] += 1
                logger.error(f"Status API 오류: {e}")
                return jsonify({'error': str(e), 'status': 'error'}), 500
        
        @self.app.route('/api/positions')
        def api_positions():
            """포지션 목록 API"""
            self.metrics['requests_count'] += 1
            
            try:
                # 캐시 확인
                cached = self._get_cached('positions')
                if cached:
                    return jsonify(cached)
                
                positions_data = self._build_positions_data()
                self._set_cache('positions', positions_data)
                return jsonify(positions_data)
                
            except Exception as e:
                self.metrics['errors_count'] += 1
                logger.error(f"Positions API 오류: {e}")
                return jsonify({'error': str(e), 'positions': []}), 500
        
        @self.app.route('/api/account')
        def api_account():
            """계좌 정보 API"""
            self.metrics['requests_count'] += 1
            
            try:
                # 캐시 확인
                cached = self._get_cached('account')
                if cached:
                    return jsonify(cached)
                
                account_data = self._build_account_data()
                self._set_cache('account', account_data)
                return jsonify(account_data)
                
            except Exception as e:
                self.metrics['errors_count'] += 1
                logger.error(f"Account API 오류: {e}")
                return jsonify({'error': str(e), 'balance': 0}), 500
        
        @self.app.route('/api/strategies')
        def api_strategies():
            """전략 정보 API"""
            self.metrics['requests_count'] += 1
            
            try:
                strategies_data = self._build_strategies_data()
                return jsonify(strategies_data)
                
            except Exception as e:
                self.metrics['errors_count'] += 1
                logger.error(f"Strategies API 오류: {e}")
                return jsonify({'error': str(e), 'strategies': []}), 500
        
        @self.app.route('/api/debug')
        def api_debug():
            """디버그 정보 API"""
            return jsonify({
                'has_position_manager': self.position_manager is not None,
                'has_binance_api': self.binance_api is not None,
                'has_strategies': bool(self.strategies),
                'position_manager_type': type(self.position_manager).__name__ if self.position_manager else None,
                'binance_api_type': type(self.binance_api).__name__ if self.binance_api else None,
                'config_system_mode': self.config.get('system', {}).get('mode', 'not_found') if self.config else 'no_config'
            })
        
        @self.app.route('/api/routes')
        def api_routes():
            """등록된 라우트 목록"""
            routes = []
            for rule in self.app.url_map.iter_rules():
                routes.append({
                    'endpoint': rule.endpoint,
                    'methods': list(rule.methods),
                    'path': str(rule)
                })
            return jsonify(routes)
        
        @self.app.route('/api/metrics')
        def api_metrics():
            """시스템 메트릭 API"""
            self.metrics['requests_count'] += 1
            
            try:
                uptime = (datetime.now() - self.metrics['start_time']).total_seconds()
                
                metrics = {
                    'uptime_seconds': uptime,
                    'uptime_formatted': self._format_uptime(uptime),
                    'requests_count': self.metrics['requests_count'],
                    'errors_count': self.metrics['errors_count'],
                    'error_rate': self.metrics['errors_count'] / max(self.metrics['requests_count'], 1),
                    'api_calls': self.metrics['api_calls'],
                    'last_sync_time': self.metrics['last_sync_time'],
                    'cache_stats': self._get_cache_stats()
                }
                
                return jsonify(metrics)
                
            except Exception as e:
                logger.error(f"Metrics API 오류: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/sync', methods=['POST'])
        def api_sync():
            """강제 동기화 API"""
            self.metrics['requests_count'] += 1
            
            try:
                # 캐시 무효화
                self._invalidate_cache()
                
                # 동기화 실행
                if self.position_manager and hasattr(self.position_manager, 'sync_positions'):
                    sync_result = self._run_async(self.position_manager.sync_positions())
                    self.metrics['last_sync_time'] = datetime.now().isoformat()
                    
                    return jsonify({
                        'success': True,
                        'sync_time': self.metrics['last_sync_time'],
                        'result': sync_result
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': 'Position manager not available'
                    }), 503
                    
            except Exception as e:
                self.metrics['errors_count'] += 1
                logger.error(f"Sync API 오류: {e}")
                return jsonify({'error': str(e), 'success': False}), 500
        
        @self.app.route('/api/config')
        def api_config():
            """설정 정보 API"""
            self.metrics['requests_count'] += 1
            
            try:
                # 민감한 정보 제외
                safe_config = self._get_safe_config()
                return jsonify(safe_config)
                
            except Exception as e:
                logger.error(f"Config API 오류: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/logs')
        def api_logs():
            """최근 로그 API"""
            self.metrics['requests_count'] += 1
            
            try:
                logs = self._get_recent_logs()
                return jsonify({
                    'logs': logs,
                    'timestamp': datetime.now().isoformat()
                })
                
            except Exception as e:
                logger.error(f"Logs API 오류: {e}")
                return jsonify({'error': str(e), 'logs': []}), 500
        
        @self.app.route('/api/health')
        def api_health():
            """헬스체크 API"""
            try:
                health = {
                    'status': 'healthy',
                    'timestamp': datetime.now().isoformat(),
                    'components': {
                        'dashboard': True,
                        'position_manager': self.position_manager is not None,
                        'binance_api': self.binance_api is not None,
                        'strategies': len(self.strategies) > 0
                    }
                }
                
                # 모든 컴포넌트가 정상이면 200, 아니면 503
                all_healthy = all(health['components'].values())
                return jsonify(health), 200 if all_healthy else 503
                
            except Exception as e:
                return jsonify({'status': 'unhealthy', 'error': str(e)}), 503
        
        # 정적 파일 서빙 (필요한 경우)
        @self.app.route('/static/<path:path>')
        def send_static(path):
            return send_from_directory('static', path)
        
        # 에러 핸들러
        @self.app.errorhandler(404)
        def not_found(error):
            self.metrics['errors_count'] += 1
            return jsonify({'error': 'Not found', 'status': 404}), 404
        
        @self.app.errorhandler(500)
        def internal_error(error):
            self.metrics['errors_count'] += 1
            return jsonify({'error': 'Internal server error', 'status': 500}), 500
    
    def _build_status(self) -> Dict[str, Any]:
        """시스템 상태 빌드"""
        uptime = (datetime.now() - self.metrics['start_time']).total_seconds()
        
        status = {
            'running': True,
            'timestamp': datetime.now().isoformat(),
            'uptime': int(uptime),
            'uptime_formatted': self._format_uptime(uptime),
            'version': '2.0',
            'environment': 'production',
            'testnet': self.config.get('system', {}).get('mode', 'live') == 'testnet'
        }
        
        # 실시간 잔고 추가 (기존 코드 유지)
        if self.binance_api:
            balance = self._run_async(self.binance_api.get_account_balance())
            if balance is not None:
                status['real_time_balance'] = float(balance)
        
        # 전략 정보 - 개선된 버전
        if self.strategies:
            strategies_list = []
            for strategy in self.strategies:
                strategy_info = {
                    'name': 'Unknown',
                    'active': True,
                    'symbols': getattr(strategy, 'symbols', [])
                }
                
                # get_strategy_info 사용 (있으면)
                if hasattr(strategy, 'get_strategy_info'):
                    try:
                        info = strategy.get_strategy_info()
                        strategy_info['name'] = info.get('name', 'Unknown')
                    except:
                        strategy_info['name'] = getattr(strategy, 'name', 'Unknown')
                else:
                    strategy_info['name'] = getattr(strategy, 'name', 'Unknown')
                
                strategies_list.append(strategy_info)
            
            status['strategies'] = strategies_list
            
            # 첫 번째 전략을 active_strategy로도 설정 (호환성)
            if strategies_list:
                status['active_strategy'] = strategies_list[0]['name']
        else:
            status['strategies'] = []
        
        # 포지션 요약 (기존 코드 유지)
        if self.position_manager:
            positions = self.position_manager.get_active_positions()
            status['positions_summary'] = {
                'total': len(positions),
                'long': sum(1 for p in positions if p.side == 'LONG'),
                'short': sum(1 for p in positions if p.side == 'SHORT'),
                'manual': sum(1 for p in positions if p.is_manual)
            }
        else:
            status['positions_summary'] = {
                'total': 0, 'long': 0, 'short': 0, 'manual': 0
            }
        
        return status
    
    def _build_positions_data(self) -> Dict[str, Any]:
        """포지션 데이터 빌드"""
        if not self.position_manager:
            return {'positions': [], 'total': 0}
        
        positions = self.position_manager.get_active_positions()
        positions_list = []
        
        for pos in positions:
            # 현재가 조회
            current_price = self._get_current_price(pos.symbol)
            if not current_price:
                current_price = pos.entry_price  # 가격 조회 실패시 진입가 사용
            
            # PnL 계산
            pnl_percent = 0
            pnl_usdt = 0
            if current_price and pos.entry_price:
                if pos.side == 'LONG':
                    pnl_percent = ((current_price - pos.entry_price) / pos.entry_price) * 100
                else:
                    pnl_percent = ((pos.entry_price - current_price) / pos.entry_price) * 100
                
                pnl_percent *= pos.leverage
                pnl_usdt = (pos.size * pos.entry_price) * (pnl_percent / 100)
            
            position_data = {
                'symbol': pos.symbol,
                'side': pos.side,
                'size': pos.size,
                'entry_price': pos.entry_price,
                'current_price': current_price,
                'leverage': pos.leverage,
                'pnl_percent': round(pnl_percent, 2),
                'pnl_usdt': round(pnl_usdt, 2),
                'is_manual': pos.is_manual,
                'strategy_name': pos.strategy_name,
                'created_at': pos.created_at,
                'stop_loss': pos.stop_loss,
                'take_profit': pos.take_profit,
                'status': pos.status
            }
            
            positions_list.append(position_data)
        
        # PnL 기준 정렬
        positions_list.sort(key=lambda x: x['pnl_percent'], reverse=True)
        
        return {
            'positions': positions_list,
            'total': len(positions_list),
            'timestamp': datetime.now().isoformat()
        }
    
    def _build_account_data(self) -> Dict[str, Any]:
        """계좌 데이터 빌드"""
        account_data = {
            'balance': 0,
            'unrealized_pnl': 0,
            'margin_balance': 0,
            'available_balance': 0,
            'timestamp': datetime.now().isoformat()
        }
        
        if self.binance_api:  # exchange 대신 binance_api 사용
            try:
                # get_account_balance 메서드 호출
                balance = self._run_async(self.binance_api.get_account_balance())
                if balance is not None:
                    account_data['balance'] = float(balance)
                    account_data['available_balance'] = float(balance)  # 임시로 동일하게 설정
                
                # 포지션에서 미실현 손익 계산
                if self.position_manager:
                    positions = self.position_manager.get_active_positions()
                    total_pnl = 0
                    for pos in positions:
                        current_price = self._get_current_price(pos.symbol)
                        if current_price and pos.entry_price:
                            if pos.side == 'LONG':
                                pnl = (current_price - pos.entry_price) * pos.size
                            else:
                                pnl = (pos.entry_price - current_price) * pos.size
                            total_pnl += pnl
                    
                    account_data['unrealized_pnl'] = round(total_pnl, 2)
                    account_data['margin_balance'] = account_data['balance'] + account_data['unrealized_pnl']
                    
            except Exception as e:
                logger.error(f"계좌 정보 조회 실패: {e}")
        
        return account_data
    
    def _build_strategies_data(self) -> Dict[str, Any]:
        """전략 데이터 빌드"""
        strategies_list = []
        
        for strategy in self.strategies:
            strategy_data = {
                'name': getattr(strategy, 'name', 'Unknown'),
                'class': strategy.__class__.__name__,
                'symbols': getattr(strategy, 'symbols', []),
                'parameters': {}
            }
            
            # 주요 파라미터 추출
            param_names = ['leverage', 'position_size', 'stop_loss_percent']
            for param in param_names:
                if hasattr(strategy, param):
                    strategy_data['parameters'][param] = getattr(strategy, param)
            
            # 성과 정보 (있는 경우)
            if hasattr(strategy, 'get_performance'):
                try:
                    strategy_data['performance'] = strategy.get_performance()
                except:
                    pass
            
            strategies_list.append(strategy_data)
        
        return {
            'strategies': strategies_list,
            'total': len(strategies_list),
            'timestamp': datetime.now().isoformat()
        }
    
    def _get_current_price(self, symbol: str) -> Optional[float]:
        """현재가 조회 (캐시 활용)"""
        try:
            # 가격 캐시 확인
            price_cache = self.cache.get('prices', {})
            cache_data = price_cache.get('data', {})
            cache_time = price_cache.get('timestamp')
            
            # 캐시가 유효한 경우
            if cache_time and (datetime.now() - cache_time).total_seconds() < price_cache.get('ttl', 2):
                if symbol in cache_data:
                    return cache_data[symbol]
            
            # BinanceAPI를 통해 가격 조회
            if self.binance_api:
                try:
                    # get_current_price 메서드 사용
                    price = self._run_async(self.binance_api.get_current_price(symbol))
                    if price:
                        # 캐시 업데이트
                        if 'prices' not in self.cache:
                            self.cache['prices'] = {'data': {}, 'timestamp': None, 'ttl': 2}
                        
                        self.cache['prices']['data'][symbol] = float(price)
                        self.cache['prices']['timestamp'] = datetime.now()
                        
                        return float(price)
                except Exception as e:
                    logger.error(f"가격 조회 실패 {symbol}: {e}")
            
            return None
            
        except Exception as e:
            logger.error(f"가격 조회 중 오류 {symbol}: {e}")
            return None
    
    def _get_safe_config(self) -> Dict[str, Any]:
        """안전한 설정 정보 반환"""
        if not self.config:
            return {}
        
        # 민감한 키 제외
        sensitive_keys = ['api_key', 'api_secret', 'bot_token', 'password']
        
        safe_config = {}
        for key, value in self.config.items():
            if isinstance(value, dict):
                safe_config[key] = {
                    k: v for k, v in value.items()
                    if not any(sensitive in k.lower() for sensitive in sensitive_keys)
                }
            elif not any(sensitive in key.lower() for sensitive in sensitive_keys):
                safe_config[key] = value
        
        return safe_config
    
    def _get_recent_logs(self, lines: int = 100) -> List[str]:
        """최근 로그 조회"""
        logs = []
        
        try:
            import glob
            log_files = glob.glob('logs/trading_*.log')
            
            if log_files:
                log_files.sort(key=os.path.getmtime, reverse=True)
                latest_log = log_files[0]
                
                with open(latest_log, 'r', encoding='utf-8') as f:
                    all_lines = f.readlines()
                    logs = [line.strip() for line in all_lines[-lines:] if line.strip()]
                    
        except Exception as e:
            logger.error(f"로그 읽기 실패: {e}")
            logs.append(f"로그 읽기 실패: {e}")
        
        return logs
    
    def _format_uptime(self, seconds: float) -> str:
        """업타임 포맷팅"""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        
        return " ".join(parts) if parts else "< 1m"
    
    def _get_cached(self, key: str) -> Optional[Any]:
        """캐시에서 데이터 조회"""
        if key not in self.cache:
            return None
        
        cache_entry = self.cache[key]
        if not cache_entry['timestamp']:
            return None
        
        age = (datetime.now() - cache_entry['timestamp']).total_seconds()
        if age < cache_entry['ttl']:
            return cache_entry['data']
        
        return None
    
    def _set_cache(self, key: str, data: Any) -> None:
        """캐시에 데이터 저장"""
        if key in self.cache:
            self.cache[key]['data'] = data
            self.cache[key]['timestamp'] = datetime.now()
    
    def _invalidate_cache(self) -> None:
        """캐시 무효화"""
        for key in self.cache:
            self.cache[key]['timestamp'] = None
    
    def _get_cache_stats(self) -> Dict[str, Any]:
        """캐시 통계"""
        stats = {}
        for key, entry in self.cache.items():
            if entry['timestamp']:
                age = (datetime.now() - entry['timestamp']).total_seconds()
                stats[key] = {
                    'age_seconds': round(age, 1),
                    'ttl_seconds': entry['ttl'],
                    'valid': age < entry['ttl']
                }
            else:
                stats[key] = {'valid': False}
        return stats
    
    def _run_async(self, coro):
        """비동기 함수 실행"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        except Exception as e:
            logger.error(f"비동기 실행 실패: {e}")
            return None
        finally:
            loop.close()
    
    def setup_performance_dashboard(self, performance_tracker=None):
        """성과 대시보드 설정"""
        if not performance_tracker and not self.performance_tracker:
            logger.warning("Performance tracker가 없어 성과 대시보드를 설정할 수 없습니다")
            return
        
        if performance_tracker:
            self.performance_tracker = performance_tracker
        
        # PerformanceDashboard 인스턴스 생성
        self.performance_dashboard = PerformanceDashboard(
            performance_tracker=self.performance_tracker,
            state_manager=self.state_manager
        )
        
        # Blueprint 등록
        self.app.register_blueprint(self.performance_dashboard.blueprint)
        
        logger.info("Performance Dashboard가 성공적으로 설정되었습니다")
    
    def _get_default_html(self) -> str:
        """기본 HTML 템플릿"""
        return '''
<!DOCTYPE html>
<html>
<head>
    <title>AlbraTrading Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .card h3 { margin-bottom: 15px; color: #2c3e50; }
        .status { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
        .status-dot { width: 10px; height: 10px; border-radius: 50%; }
        .status-dot.active { background: #27ae60; }
        .status-dot.inactive { background: #e74c3c; }
        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 12px; border-bottom: 1px solid #eee; }
        th { background: #f8f9fa; font-weight: 600; }
        .positive { color: #27ae60; }
        .negative { color: #e74c3c; }
        .refresh-btn { 
            background: #3498db; 
            color: white; 
            border: none; 
            padding: 8px 16px; 
            border-radius: 4px; 
            cursor: pointer;
            font-size: 14px;
        }
        .refresh-btn:hover { background: #2980b9; }
        .loading { opacity: 0.6; }
        .error { background: #fee; color: #c33; padding: 10px; border-radius: 4px; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>AlbraTrading System Dashboard</h1>
            <div class="status">
                <span class="status-dot active" id="status-dot"></span>
                <span id="status-text">Connecting...</span>
                <button class="refresh-btn" onclick="refreshAll()">Refresh</button>
            </div>
        </div>
        
        <div class="grid">
            <div class="card">
                <h3>System Status</h3>
                <div id="system-info">Loading...</div>
            </div>
            
            <div class="card">
                <h3>Account</h3>
                <div id="account-info">Loading...</div>
            </div>
            
            <div class="card">
                <h3>Active Strategies</h3>
                <div id="strategies-info">Loading...</div>
            </div>
        </div>
        
        <div class="card" style="margin-top: 20px;">
            <h3>Active Positions</h3>
            <div id="positions-table">Loading...</div>
        </div>
    </div>
    
    <script>
        let updateInterval;
        
        async function fetchData(endpoint) {
            try {
                const response = await fetch(endpoint);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return await response.json();
            } catch (error) {
                console.error(`Failed to fetch ${endpoint}:`, error);
                throw error;
            }
        }
        
        async function updateStatus() {
            try {
                const status = await fetchData('/api/status');
                document.getElementById('status-dot').className = 'status-dot active';
                document.getElementById('status-text').textContent = `Running - Uptime: ${status.uptime_formatted || 'N/A'}`;
                
                // System info
                const systemHtml = `
                    <div class="status">Strategies: ${status.strategies?.length || 0}</div>
                    <div class="status">Positions: ${status.positions_summary?.total || 0}</div>
                    <div class="status">Long/Short: ${status.positions_summary?.long || 0}/${status.positions_summary?.short || 0}</div>
                `;
                document.getElementById('system-info').innerHTML = systemHtml;
            } catch (error) {
                document.getElementById('status-dot').className = 'status-dot inactive';
                document.getElementById('status-text').textContent = 'Disconnected';
                document.getElementById('system-info').innerHTML = '<div class="error">Connection failed</div>';
            }
        }
        
        async function updateAccount() {
            try {
                const account = await fetchData('/api/account');
                const balance = account.balance || 0;
                const pnl = account.unrealized_pnl || 0;
                const pnlClass = pnl >= 0 ? 'positive' : 'negative';
                
                const accountHtml = `
                    <div>Balance: ${balance.toFixed(2)} USDT</div>
                    <div>Unrealized PnL: <span class="${pnlClass}">${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)} USDT</span></div>
                    <div>Available: ${(account.available_balance || 0).toFixed(2)} USDT</div>
                `;
                document.getElementById('account-info').innerHTML = accountHtml;
            } catch (error) {
                document.getElementById('account-info').innerHTML = '<div class="error">Failed to load account</div>';
            }
        }
        
        async function updateStrategies() {
            try {
                const data = await fetchData('/api/strategies');
                const strategies = data.strategies || [];
                
                if (strategies.length === 0) {
                    document.getElementById('strategies-info').innerHTML = '<div>No active strategies</div>';
                    return;
                }
                
                const strategyHtml = strategies.map(s => `
                    <div class="status">
                        <strong>${s.name}</strong> - ${s.symbols?.length || 0} symbols
                    </div>
                `).join('');
                
                document.getElementById('strategies-info').innerHTML = strategyHtml;
            } catch (error) {
                document.getElementById('strategies-info').innerHTML = '<div class="error">Failed to load strategies</div>';
            }
        }
        
        async function updatePositions() {
            try {
                const data = await fetchData('/api/positions');
                const positions = data.positions || [];
                
                if (positions.length === 0) {
                    document.getElementById('positions-table').innerHTML = '<div>No active positions</div>';
                    return;
                }
                
                const tableHtml = `
                    <table>
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Side</th>
                                <th>Size</th>
                                <th>Entry</th>
                                <th>Current</th>
                                <th>PnL %</th>
                                <th>PnL USDT</th>
                                <th>Type</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${positions.map(p => `
                                <tr>
                                    <td>${p.symbol}</td>
                                    <td>${p.side}</td>
                                    <td>${p.size.toFixed(4)}</td>
                                    <td>${p.entry_price.toFixed(2)}</td>
                                    <td>${p.current_price.toFixed(2)}</td>
                                    <td class="${p.pnl_percent >= 0 ? 'positive' : 'negative'}">
                                        ${p.pnl_percent >= 0 ? '+' : ''}${p.pnl_percent.toFixed(2)}%
                                    </td>
                                    <td class="${p.pnl_usdt >= 0 ? 'positive' : 'negative'}">
                                        ${p.pnl_usdt >= 0 ? '+' : ''}${p.pnl_usdt.toFixed(2)}
                                    </td>
                                    <td>${p.is_manual ? 'Manual' : p.strategy_name || 'Auto'}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `;
                
                document.getElementById('positions-table').innerHTML = tableHtml;
            } catch (error) {
                document.getElementById('positions-table').innerHTML = '<div class="error">Failed to load positions</div>';
            }
        }
        
        async function refreshAll() {
            document.body.classList.add('loading');
            await Promise.all([
                updateStatus(),
                updateAccount(),
                updateStrategies(),
                updatePositions()
            ]);
            document.body.classList.remove('loading');
        }
        
        // 초기 로드
        refreshAll();
        
        // 5초마다 자동 업데이트
        updateInterval = setInterval(refreshAll, 5000);
        
        // 페이지 언로드 시 인터벌 정리
        window.addEventListener('beforeunload', () => {
            if (updateInterval) clearInterval(updateInterval);
        });
    </script>
</body>
</html>
        '''


# 전역 인스턴스
_dashboard_app = None


def create_dashboard(position_manager, strategies, config):
    """레거시 호환성을 위한 create_dashboard 함수"""
    global _dashboard_app
    
    try:
        # DashboardApp 인스턴스 생성
        _dashboard_app = DashboardApp()
        
        # 시스템 컴포넌트 연결
        _dashboard_app.position_manager = position_manager
        _dashboard_app.strategies = strategies if isinstance(strategies, list) else [strategies]
        _dashboard_app.config = config
        
        # BinanceAPI 연결 수정 - exchange가 아닌 binance_api 사용
        if hasattr(position_manager, 'binance_api'):
            _dashboard_app.binance_api = position_manager.binance_api
            logger.info("BinanceAPI 연결 성공")
        else:
            logger.warning("position_manager에 binance_api가 없습니다")
        
        # State Manager 연결
        if hasattr(position_manager, 'state_manager'):
            _dashboard_app.state_manager = position_manager.state_manager
        
        # Notification Manager 연결
        if hasattr(position_manager, 'notification_manager'):
            _dashboard_app.notification_manager = position_manager.notification_manager
        
        logger.info("대시보드 시작: http://0.0.0.0:5000")
        
        # Flask 앱 실행
        _dashboard_app.app.run(
            host='0.0.0.0',
            port=5000,
            debug=False,
            use_reloader=False,
            threaded=True
        )
        
    except Exception as e:
        logger.error(f"대시보드 시작 실패: {e}")
        raise


def get_dashboard_app():
    """대시보드 앱 인스턴스 반환"""
    return _dashboard_app