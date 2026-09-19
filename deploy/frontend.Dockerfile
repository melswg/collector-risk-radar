FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend .
RUN npm run build
FROM nginx:alpine
RUN apk add --no-cache openssl && mkdir -p /etc/nginx/tls && openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/nginx/tls/key.pem -out /etc/nginx/tls/cert.pem -subj '/CN=localhost' -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1'
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
