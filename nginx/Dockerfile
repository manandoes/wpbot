# Stage 1: Build the React dashboard
FROM node:20-alpine AS builder

WORKDIR /build

COPY dashboard/package*.json ./
RUN npm ci

COPY dashboard/ .

# Empty VITE_API_URL means all API calls are relative (same origin, proxied by nginx)
ENV VITE_API_URL=

RUN npm run build

# Stage 2: Nginx serves static files + proxies API
FROM nginx:1.27-alpine

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
