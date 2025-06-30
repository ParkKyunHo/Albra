#!/usr/bin/env python3
"""
오류 추적 및 분석 도구
로그 파일에서 오류를 수집하고 패턴을 분석합니다.
"""

import os
import re
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Tuple, Optional

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent
CLAUDE_DIR = PROJECT_ROOT / '.claude'
LOGS_DIR = PROJECT_ROOT / 'logs'

class ErrorTracker:
    def __init__(self):
        self.errors = []
        self.patterns = defaultdict(int)
        
    def scan_log_files(self, days: int = 7) -> List[Dict]:
        """로그 파일에서 오류 스캔"""
        errors = []
        since_date = datetime.now() - timedelta(days=days)
        
        # 로그 파일 패턴
        log_patterns = ['*.log', '*_error.log']
        
        for pattern in log_patterns:
            for log_file in LOGS_DIR.glob(pattern):
                if log_file.stat().st_mtime < since_date.timestamp():
                    continue
                    
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        for line_num, line in enumerate(f, 1):
                            error_info = self._parse_error_line(line, log_file, line_num)
                            if error_info:
                                errors.append(error_info)
                except Exception as e:
                    print(f"로그 파일 읽기 실패 {log_file}: {e}")
        
        return errors
    
    def _parse_error_line(self, line: str, file_path: Path, line_num: int) -> Optional[Dict]:
        """오류 라인 파싱"""
        # 오류 패턴들
        error_patterns = [
            (r'ERROR', 'ERROR'),
            (r'CRITICAL', 'CRITICAL'),
            (r'Exception:', 'EXCEPTION'),
            (r'Traceback', 'TRACEBACK'),
            (r'Failed', 'FAILED'),
            (r'Error:', 'ERROR'),
        ]
        
        for pattern, error_type in error_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                # 타임스탬프 추출
                timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                timestamp = timestamp_match.group(1) if timestamp_match else 'Unknown'
                
                return {
                    'timestamp': timestamp,
                    'type': error_type,
                    'file': file_path.name,
                    'line_num': line_num,
                    'message': line.strip(),
                    'full_path': str(file_path)
                }
        
        return None
    
    def find_related_commits(self, error_date: str) -> List[str]:
        """오류 수정 관련 커밋 찾기"""
        try:
            # 오류 날짜 이후의 fix 커밋 찾기
            result = subprocess.run(
                ['git', 'log', f'--since={error_date}', '--grep=fix', '--oneline'],
                capture_output=True, text=True, cwd=PROJECT_ROOT
            )
            if result.stdout:
                return result.stdout.strip().split('\n')[:5]
        except:
            pass
        return []
    
    def analyze_patterns(self, errors: List[Dict]) -> Dict[str, any]:
        """오류 패턴 분석"""
        analysis = {
            'total_errors': len(errors),
            'by_type': defaultdict(int),
            'by_file': defaultdict(int),
            'by_hour': defaultdict(int),
            'common_messages': defaultdict(int)
        }
        
        for error in errors:
            # 타입별 집계
            analysis['by_type'][error['type']] += 1
            
            # 파일별 집계
            analysis['by_file'][error['file']] += 1
            
            # 시간대별 집계
            if error['timestamp'] != 'Unknown':
                try:
                    hour = datetime.strptime(error['timestamp'], '%Y-%m-%d %H:%M:%S').hour
                    analysis['by_hour'][hour] += 1
                except:
                    pass
            
            # 메시지 패턴
            # 숫자, UUID 등을 제거하여 패턴화
            cleaned_msg = re.sub(r'\d+', 'N', error['message'])
            cleaned_msg = re.sub(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', 'UUID', cleaned_msg)
            analysis['common_messages'][cleaned_msg[:100]] += 1
        
        # 가장 빈번한 메시지만 유지
        analysis['common_messages'] = dict(
            sorted(analysis['common_messages'].items(), 
                   key=lambda x: x[1], reverse=True)[:10]
        )
        
        return dict(analysis)
    
    def generate_report(self, output_file: Optional[str] = None):
        """오류 분석 리포트 생성"""
        print("🔍 오류 추적 시작...")
        
        # 최근 7일 오류 스캔
        errors = self.scan_log_files(days=7)
        print(f"✅ {len(errors)}개의 오류 발견")
        
        # 패턴 분석
        analysis = self.analyze_patterns(errors)
        
        # 리포트 생성
        report = {
            'generated_at': datetime.now().isoformat(),
            'summary': {
                'total_errors': analysis['total_errors'],
                'unique_files': len(analysis['by_file']),
                'error_types': dict(analysis['by_type'])
            },
            'patterns': {
                'by_type': dict(analysis['by_type']),
                'by_file': dict(analysis['by_file']),
                'by_hour': dict(analysis['by_hour']),
                'common_messages': analysis['common_messages']
            },
            'recent_errors': errors[:20]  # 최근 20개
        }
        
        # 오류 히스토리 업데이트
        self._update_error_history(errors, analysis)
        
        # JSON 리포트 저장
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print(f"📄 리포트 저장: {output_file}")
        
        # 콘솔 출력
        self._print_summary(analysis)
        
        return report
    
    def _update_error_history(self, errors: List[Dict], analysis: Dict):
        """ERROR_HISTORY.md 파일 업데이트"""
        history_file = CLAUDE_DIR / 'ERROR_HISTORY.md'
        
        if not history_file.exists():
            return
        
        # 새로운 섹션 추가
        today = datetime.now().strftime('%Y-%m-%d')
        new_section = f"\n### {today}: 자동 스캔 결과\n"
        new_section += f"- **스캔된 오류**: {len(errors)}개\n"
        new_section += f"- **주요 타입**: {', '.join(f'{k}({v})' for k, v in list(analysis['by_type'].items())[:3])}\n"
        new_section += "- **상태**: 🔍 분석 중\n"
        
        # 가장 빈번한 오류 추가
        if analysis['common_messages']:
            new_section += "- **빈번한 오류**:\n"
            for msg, count in list(analysis['common_messages'].items())[:3]:
                new_section += f"  - {msg[:50]}... ({count}회)\n"
        
        # 파일에 추가
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 적절한 위치에 삽입
            if '## 2025년' in content:
                parts = content.split('## 2025년', 1)
                content = parts[0] + '## 2025년' + new_section + parts[1]
            else:
                content += f"\n## {datetime.now().year}년\n" + new_section
            
            with open(history_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print("✅ ERROR_HISTORY.md 업데이트 완료")
        except Exception as e:
            print(f"❌ 히스토리 업데이트 실패: {e}")
    
    def _print_summary(self, analysis: Dict):
        """콘솔에 요약 출력"""
        print("\n" + "="*50)
        print("📊 오류 분석 요약")
        print("="*50)
        
        print(f"\n총 오류 수: {analysis['total_errors']}")
        
        print("\n오류 타입별:")
        for error_type, count in sorted(analysis['by_type'].items(), key=lambda x: x[1], reverse=True):
            print(f"  - {error_type}: {count}개")
        
        print("\n파일별 오류:")
        for file_name, count in sorted(analysis['by_file'].items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  - {file_name}: {count}개")
        
        print("\n시간대별 분포:")
        peak_hours = sorted(analysis['by_hour'].items(), key=lambda x: x[1], reverse=True)[:3]
        for hour, count in peak_hours:
            print(f"  - {hour:02d}시: {count}개")
        
        print("\n💡 권장사항:")
        if analysis['total_errors'] > 100:
            print("  - 오류가 많습니다. 시스템 안정성 점검 필요")
        if peak_hours and peak_hours[0][1] > analysis['total_errors'] * 0.3:
            print(f"  - {peak_hours[0][0]}시에 오류 집중. 해당 시간대 부하 확인 필요")
        if 'CRITICAL' in analysis['by_type']:
            print("  - CRITICAL 오류 발견. 즉시 조치 필요")

def main():
    """메인 실행 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description='오류 추적 및 분석')
    parser.add_argument('--days', type=int, default=7, help='분석할 일수')
    parser.add_argument('--output', type=str, help='리포트 출력 파일')
    parser.add_argument('--update-history', action='store_true', help='ERROR_HISTORY.md 업데이트')
    
    args = parser.parse_args()
    
    tracker = ErrorTracker()
    report = tracker.generate_report(output_file=args.output)
    
    print("\n✅ 오류 추적 완료!")

if __name__ == "__main__":
    main()