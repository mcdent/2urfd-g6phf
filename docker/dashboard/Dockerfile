# Dashboard – nginx + php-fpm
# Build context: /home/mike/source/2urfd

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    nginx \
    php-fpm \
    php-curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dashboard files
RUN mkdir -p /var/www/html
COPY dashboard/ /var/www/html/
RUN chown -R www-data:www-data /var/www/html

# ── nginx config – logs go to /logs/ ─────────────────────────────────────────
RUN sed -i \
    's|error_log /var/log/nginx/error.log;|error_log /logs/nginx-error.log;|' \
    /etc/nginx/nginx.conf \
    && sed -i \
    's|access_log /var/log/nginx/access.log;|access_log /logs/nginx-access.log;|' \
    /etc/nginx/nginx.conf

# ── nginx site config ─────────────────────────────────────────────────────────
RUN PHP_VER=$(php -r 'echo PHP_MAJOR_VERSION.".".PHP_MINOR_VERSION;') && \
cat > /etc/nginx/sites-available/urfd << EOF
server {
    listen 80;
    server_name _;
    root /var/www/html;
    index index.php index.html;

    access_log /logs/nginx-access.log;
    error_log  /logs/nginx-error.log;

    location / {
        try_files \$uri \$uri/ /index.php?\$args;
    }

    location ~ \.php$ {
        include snippets/fastcgi-php.conf;
        fastcgi_pass unix:/run/php/php${PHP_VER}-fpm.sock;
    }

    location /urfd.xml {
        alias /logs/urfd.xml;
        default_type application/xml;
    }
}
EOF

RUN ln -sf /etc/nginx/sites-available/urfd /etc/nginx/sites-enabled/urfd \
    && rm -f /etc/nginx/sites-enabled/default

# ── Entrypoint ────────────────────────────────────────────────────────────────
RUN cat > /entrypoint.sh << 'SCRIPT'
#!/bin/bash
set -e

mkdir -p /logs /run/php
chmod o+w /logs   # allow www-data (uid 33) to write callinghome.php etc.

PHP_VER=$(php -r 'echo PHP_MAJOR_VERSION.".".PHP_MINOR_VERSION;')
php-fpm${PHP_VER} --nodaemonize &

exec nginx -g 'daemon off;'
SCRIPT
RUN chmod +x /entrypoint.sh

EXPOSE 80

ENTRYPOINT ["/entrypoint.sh"]
