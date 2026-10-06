FROM nginx:1

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY ./landing/nginx.conf /etc/nginx/conf.d/default.conf

# Stored as a template so FRONTEND_URL can be injected at container startup.
COPY ./landing/index.html /usr/share/nginx/html/index.html.template

COPY ./landing/privacy.html /usr/share/nginx/html/privacy.html
COPY ./landing/fonts /usr/share/nginx/html/fonts
COPY ./landing/assets /usr/share/nginx/html/assets

COPY ./landing/docker-entrypoint.sh /docker-entrypoint.d/40-envsubst-html.sh
RUN chmod +x /docker-entrypoint.d/40-envsubst-html.sh
