#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
CERTS_DIR="$ROOT/.certs"

SSL=false
NO_AUTOLOGIN=false
BACKEND_UP=false

usage() {
  echo "Usage: ./start.sh [OPTIONS]"
  echo ""
  echo "Options:"
  echo "  --ssl             Enable HTTPS (auto-generates self-signed cert)"
  echo "  --no-autologin    Disable auto-login to test the login page"
  echo "  -h, --help        Show this help"
  exit 0
}

while [[ $# -gt 0 ]]; do
  case $1 in
    --ssl) SSL=true; shift ;;
    --no-autologin) NO_AUTOLOGIN=true; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

export TYPECAST_AUTH_MODE=local
if [ "$NO_AUTOLOGIN" = true ]; then
  export TYPECAST_NO_AUTOLOGIN=1
fi

if [ "$SSL" = true ]; then
  export TYPECAST_SSL=1
  mkdir -p "$CERTS_DIR"
  if [ ! -f "$CERTS_DIR/localhost.pem" ] || [ ! -f "$CERTS_DIR/localhost-key.pem" ]; then
    echo "Generating self-signed certificate..."
    openssl req -x509 -newkey rsa:2048 -nodes \
      -keyout "$CERTS_DIR/localhost-key.pem" \
      -out "$CERTS_DIR/localhost.pem" \
      -days 365 \
      -subj "/CN=localhost" \
      -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
      2>/dev/null
    echo "Certificate generated at $CERTS_DIR/"
  fi
  export TYPECAST_SSL_CERTFILE="$CERTS_DIR/localhost.pem"
  export TYPECAST_SSL_KEYFILE="$CERTS_DIR/localhost-key.pem"
fi

cleanup() {
  echo "Shutting down..."
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
  wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
  echo "Done."
}
trap cleanup EXIT INT TERM

VENV_PYTHON="$ROOT/backend/.venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
  echo "No virtualenv at backend/.venv. Create it first:" >&2
  echo "  cd backend && python3 -m venv .venv && .venv/bin/python -m pip install -e \".[dev]\"" >&2
  exit 1
fi

echo "Starting backend on :8000..."
UVICORN_ARGS="app.main:app --reload --host 0.0.0.0 --port 8000"
if [ "$SSL" = true ]; then
  UVICORN_ARGS="$UVICORN_ARGS --ssl-keyfile $TYPECAST_SSL_KEYFILE --ssl-certfile $TYPECAST_SSL_CERTFILE"
fi
cd "$ROOT/backend"
# Invoked as a module, not as .venv/bin/uvicorn. Console scripts carry an absolute
# shebang from wherever the virtualenv was first created, so they break with
# "bad interpreter" if the project directory is ever moved.
"$VENV_PYTHON" -m uvicorn $UVICORN_ARGS &
BACKEND_PID=$!

echo "Starting frontend on :3000..."
cd "$ROOT/frontend"
if [ "$SSL" = true ]; then
  VITE_SSL=1 npx vite --port 3000 &
else
  npx vite --port 3000 &
fi
FRONTEND_PID=$!

PROTOCOL="http"
[ "$SSL" = true ] && PROTOCOL="https"

# Do not claim success until the backend answers. It used to print "Typecast
# running" unconditionally, so a backend that died on startup looked like a
# working app with a puzzling error scrolled above it.
echo "Waiting for the backend..."
for _ in $(seq 1 30); do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "" >&2
    echo "Backend exited during startup. Its error is above." >&2
    exit 1
  fi
  if curl -sk -o /dev/null "${PROTOCOL}://localhost:8000/api/health"; then
    BACKEND_UP=true
    break
  fi
  sleep 1
done
if [ "$BACKEND_UP" != true ]; then
  echo "" >&2
  echo "Backend did not answer ${PROTOCOL}://localhost:8000/api/health within 30s." >&2
  exit 1
fi

echo ""
echo "Typecast running — ${PROTOCOL}://localhost:3000"
if [ "$NO_AUTOLOGIN" = true ]; then
  echo "  Auto-login disabled — login: local@typecast.local / typecast"
fi
[ "$SSL" = true ] && echo "  SSL enabled (self-signed cert — browser may warn)"
echo ""

wait
