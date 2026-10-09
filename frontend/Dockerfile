# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# Stage 2: Serve over HTTPS
FROM nginx:alpine

# openssl generates a self-signed certificate on first start when none is
# mounted; the base image does not include it.
RUN apk add --no-cache openssl \
    && rm /etc/nginx/conf.d/default.conf

# Installed as a template so the official entrypoint substitutes
# ${TYPECAST_HTTPS_PORT} into the HTTP-to-HTTPS redirect at start.
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY docker-entrypoint.d/40-typecast-tls.sh /docker-entrypoint.d/40-typecast-tls.sh

COPY --from=builder /app/dist /usr/share/nginx/html

ENV TYPECAST_HTTPS_PORT=443
ENV TYPECAST_TLS_HOSTNAME=localhost

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
