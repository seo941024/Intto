#!/usr/bin/env bash
# 인또를 학교 VM에 올린다. 소스를 보내 VM에서 이미지를 빌드하고 intto 컨테이너만 새로 띄운다.
# VM의 다른 컨테이너는 건드리지 않는다.
# 사용: Git Bash에서  bash tools/deploy_vm.sh
set -euo pipefail

HOST="${INTTO_HOST:-MyAISWServer}"
KEY="${INTTO_KEY:-$HOME/.ssh/moa_vm_ed25519}"
PORT="${INTTO_PORT:-3000}"
REMOTE_DIR="intto"

cd "$(dirname "$0")/.."
SSH=(ssh -o BatchMode=yes -i "$KEY" "$HOST")

echo "소스 보내는 중 → $HOST:~/$REMOTE_DIR"
tar czf - package.json package-lock.json Dockerfile .dockerignore server shared public |
  "${SSH[@]}" "rm -rf ~/$REMOTE_DIR.new && mkdir -p ~/$REMOTE_DIR.new && tar xzf - -C ~/$REMOTE_DIR.new && rm -rf ~/$REMOTE_DIR && mv ~/$REMOTE_DIR.new ~/$REMOTE_DIR"

echo "VM에서 이미지 빌드하고 컨테이너 교체"
# 지난번 인또 이미지만 지운다. 다른 프로젝트 이미지는 건드리지 않는다
# --pull로 바탕 node 이미지를 늘 새로 받는다. --init은 종료 신호를 node에 넘기고 남은 자식 프로세스를 거둔다
# 상태 확인은 서버가 뜰 때까지 1초 간격으로 10번 다시 묻고, 끝내 응답이 없거나 오류면 배포를 실패로 끝낸다.
# 막 뜨는 서버는 연결을 끊기도 하므로 거절뿐 아니라 모든 오류를 다시 묻는다
"${SSH[@]}" "cd ~/$REMOTE_DIR && OLD=\$(docker images -q intto:latest) && docker build --pull -q -t intto:latest . \
  && (docker rm -f intto >/dev/null 2>&1 || true) \
  && docker run -d --init --name intto -p $PORT:3000 --restart unless-stopped intto:latest >/dev/null \
  && curl -fsS --retry 10 --retry-all-errors --retry-delay 1 localhost:$PORT/healthz && echo \
  && NEW=\$(docker images -q intto:latest) \
  && if [ -n \"\$OLD\" ] && [ \"\$OLD\" != \"\$NEW\" ]; then docker rmi \"\$OLD\" >/dev/null 2>&1 || true; fi"

echo "접속 주소: http://$(ssh -G "$HOST" | awk '/^hostname /{print $2}'):$PORT"
