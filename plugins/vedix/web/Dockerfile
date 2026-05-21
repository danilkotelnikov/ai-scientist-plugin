# syntax=docker/dockerfile:1.7

# ---- Build stage --------------------------------------------------------
FROM node:20-alpine AS build
WORKDIR /app

# Install dependencies first so the layer is cached across source changes.
# We copy lockfile if it exists; npm install handles either case.
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# Copy the rest of the source.
COPY . .

# Allow callers to pin VITE_API_BASE at build time:
#   docker build --build-arg VITE_API_BASE=https://api.vedix.ai .
ARG VITE_API_BASE=https://api.vedix.ai
ENV VITE_API_BASE=${VITE_API_BASE}

RUN npm run build

# ---- Runtime stage ------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# Replace the default nginx site with our SPA-aware config.
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O - http://127.0.0.1/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
