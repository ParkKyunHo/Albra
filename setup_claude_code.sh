#!/bin/bash
# Claude Code 작업 환경 설정 스크립트

echo "================================"
echo "AlbraTrading 프로젝트 환경 설정"
echo "================================"

# 1. 현재 디렉토리 확인
echo -e "\n1. 현재 디렉토리:"
pwd

# 2. Python 환경 확인
echo -e "\n2. Python 버전:"
python --version

# 3. 필수 파일 확인
echo -e "\n3. 프로젝트 문서 확인:"
for file in PROJECT_CONTEXT.md CODE_STYLE_GUIDE.md CLAUDE_CODE_INSTRUCTIONS.md WORK_HISTORY.md; do
    if [ -f "$file" ]; then
        echo "✓ $file - 존재"
    else
        echo "✗ $file - 없음"
    fi
done

# 4. 주요 소스 파일 확인
echo -e "\n4. 주요 소스 파일:"
for file in turtle_trading_strategy.py portfolio_comparison_analysis.py; do
    if [ -f "$file" ]; then
        echo "✓ $file - 존재"
    else
        echo "✗ $file - 없음"
    fi
done

# 5. 최근 수정 파일
echo -e "\n5. 최근 수정된 파일 (최근 7일):"
find . -type f -name "*.py" -mtime -7 -exec ls -la {} \; | head -10

# 6. 프로젝트 컨텍스트 미리보기
echo -e "\n6. 프로젝트 컨텍스트 (처음 20줄):"
head -20 PROJECT_CONTEXT.md

echo -e "\n================================"
echo "환경 설정 완료!"
echo "다음 명령어로 작업을 시작하세요:"
echo "  - 컨텍스트 확인: cat PROJECT_CONTEXT.md"
echo "  - 코드 스타일 확인: cat CODE_STYLE_GUIDE.md"
echo "  - 작업 이력 확인: cat WORK_HISTORY.md"
echo "================================"
