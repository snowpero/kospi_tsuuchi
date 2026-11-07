# KOSPI Telegram Alert

5분마다 KOSPI(^KS11) 지수를 조회하고, 4,000 이상 또는 3,800 이하일 때 매 실행마다 텔레그램 메시지를 전송합니다.

## 텔레그램 설정

1. 텔레그램에서 `@BotFather`에게 `/newbot`을 보내 봇을 만들고 토큰을 받습니다.
2. 만든 봇과 대화를 열고 `/start`를 보냅니다.
3. 브라우저에서 `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`를 열어 `message.chat.id` 값을 확인합니다. `<YOUR_TOKEN>`은 실제 토큰으로 바꿉니다. 토큰 URL을 타인에게 공유하지 마세요.
4. GitHub 저장소의 **Settings → Secrets and variables → Actions → New repository secret**에서 다음 두 개를 추가합니다.
   - `TELEGRAM_BOT_TOKEN`: BotFather가 발급한 토큰
   - `TELEGRAM_CHAT_ID`: `message.chat.id` 값

## GitHub 설정

1. 이 프로젝트의 파일과 `.github/workflows/kospi-alert.yml`을 새 GitHub 저장소의 **기본 브랜치**에 업로드합니다.
2. 저장소 **Actions** 탭에서 워크플로를 활성화합니다.
3. **Actions → KOSPI Telegram Alert → Run workflow**로 수동 실행을 시험합니다. 장외 시간에는 정상적으로 알림을 보내지 않습니다.
4. 평일 한국 시간 09:00~15:30에 약 5분마다 자동 실행됩니다. GitHub 예약 작업은 지연되거나 누락될 수 있습니다.

## 로컬 테스트

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN='your-token'
export TELEGRAM_CHAT_ID='your-chat-id'
python main.py
```

Windows PowerShell에서는 `export` 대신 `$env:TELEGRAM_BOT_TOKEN="..."` 형식을 사용하세요.

## 유의사항

- Yahoo Finance 비공식 데이터(yfinance)를 사용합니다. 실시간 시세가 아니거나, 제공이 중단되거나, 시세가 지연될 수 있습니다.
- 데이터가 20분보다 오래되면 메시지를 보내지 않고 실행을 실패 처리합니다.
- 한국 증시 휴장일을 별도로 조회하지 않지만 오래된 데이터 전송을 차단합니다.
- 조건 충족 중에는 **매 실행마다 반복 발송**합니다. 지수가 정상 범위에 있으면 발송하지 않습니다.
- GitHub Actions 사용량과 저장소 정책은 계정 및 저장소 유형에 따라 달라집니다.
- 토큰을 소스 코드에 넣거나 공개 저장소에 커밋하지 마세요.
