#!/bin/sh
# If certificates are missing, create a private CA and server cert (no certbot), store root at rootCA.pem.
set -e
D="${TLS_CERT_DIR:-/certs}"
mkdir -p "$D"
if [ ! -f "$D/server.crt" ] || [ ! -f "$D/server.key" ]; then
  echo "Generating self-signed CA and server certificate in $D"
  openssl genrsa -out "$D/rootCA.key" 4096
  openssl req -x509 -new -nodes -key "$D/rootCA.key" -sha256 -days 3650 \
    -out "$D/rootCA.pem" -subj "/O=R3/OU=Dev/CN=R3-Dev-Root"
  openssl genrsa -out "$D/server.key" 2048
  openssl req -new -key "$D/server.key" -out "$D/server.csr" -subj "/O=R3/OU=Web/CN=localhost"
  cat > "$D/san.ext" <<'EOF'
subjectAltName=DNS:localhost,IP:127.0.0.1
EOF
  openssl x509 -req -in "$D/server.csr" -CA "$D/rootCA.pem" -CAkey "$D/rootCA.key" -CAcreateserial \
    -out "$D/server.crt" -days 825 -sha256 -extfile "$D/san.ext"
  echo "Done. Trust rootCA.pem; download from GET /api/tls/root-ca on the API."
fi
exec nginx -g "daemon off;"
