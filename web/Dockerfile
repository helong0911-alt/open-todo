FROM node:20-alpine AS build

WORKDIR /app

COPY web/package.json web/package-lock.json* /app/
RUN npm ci

COPY web/ /app/

RUN npm run build

FROM nginx:alpine

# Copy built assets
COPY --from=build /app/dist /usr/share/nginx/html

# Nginx config: SPA fallback + API proxy
COPY web/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
