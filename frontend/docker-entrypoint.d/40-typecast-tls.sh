#!/bin/sh
# Ensure nginx has a certificate before it starts.
#
# A real certificate mounted at /etc/nginx/certs/tls.crt and tls.key is used
# as-is. Otherwise a self-signed one is generated once and kept in that
# directory, which docker-compose.yml backs with a volume so the browser
# exception you accept survives rebuilds.
set -eu

dir=/etc/nginx/certs
crt="$dir/tls.crt"
key="$dir/tls.key"
host="${TYPECAST_TLS_HOSTNAME:-localhost}"

if [ -s "$crt" ] && [ -s "$key" ]; then
    echo "typecast-tls: using the certificate in $dir"
    exit 0
fi

mkdir -p "$dir"
# 825 days is the longest validity browsers accept for a leaf certificate.
openssl req -x509 -newkey rsa:2048 -nodes -days 825 -sha256 \
    -keyout "$key" -out "$crt" -subj "/CN=$host" \
    -addext "subjectAltName=DNS:$host,DNS:localhost,IP:127.0.0.1" \
    -addext "extendedKeyUsage=serverAuth" >/dev/null 2>&1
chmod 600 "$key"
echo "typecast-tls: generated a self-signed certificate for $host (browsers will warn;"
echo "typecast-tls: mount a real tls.crt and tls.key at $dir to replace it)"
