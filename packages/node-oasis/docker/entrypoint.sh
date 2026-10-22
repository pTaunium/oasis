#!/bin/sh
set -e

BASE_URL="${BASE_URL:-http://localhost:8080}"
# Remove trailing slash if present to prevent double slashes in URLs
BASE_URL="${BASE_URL%/}"

# If the external reverse proxy already rewrites the path (e.g., nginx rewrite-target),
# force Nginx inside the container to serve at the root path (/).
if [ "${PROXY_REWRITES_PATH:-false}" = "true" ]; then
    export URL_PREFIX=""
else
    # Extract path prefix from BASE_URL (e.g., https://example.com/node-mirror -> /node-mirror)
    export URL_PREFIX=$(echo "$BASE_URL" | sed -E 's|^https?://[^/]+||')
fi

# We rely on nginx's native /docker-entrypoint.sh to process /etc/nginx/templates/*.template
# which will automatically pick up URL_PREFIX and generate /etc/nginx/conf.d/default.conf

# Safely escape BASE_URL for sed replacement (escape backslashes, ampersands, and delimiter #)
ESCAPED_BASE_URL=$(echo "$BASE_URL" | sed -e 's/[\\&#]/\\&/g')

# Replace {{BASE_URL}} in tool setup script templates
for template in /usr/share/nginx/html/tools/*/setup-*.sh.template; do
    if [ -f "$template" ]; then
        output="${template%.template}"
        sed "s#{{BASE_URL}}#${ESCAPED_BASE_URL}#g" "$template" > "$output"
        chmod +x "$output"
    fi
done

echo "=== node-oasis ==="
echo "BASE_URL:    ${BASE_URL}"
echo "NVM mirror:  ${BASE_URL}/dist"
echo "fnm mirror:  ${BASE_URL}/dist"
echo "NVM setup:   ${BASE_URL}/tools/nvm/setup-nvm.sh"
echo "fnm setup:   ${BASE_URL}/tools/fnm/setup-fnm.sh"
echo "================="

exec /docker-entrypoint.sh nginx -g 'daemon off;'
