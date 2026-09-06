# =====================================================================
# Dockerfile — packaging the Angular application
# =====================================================================
#
# WHY CONTAINERISE SOMETHING THAT IS JUST FILES?
#
# The Angular app compiles to plain HTML, CSS and JavaScript, and the planned
# production host (Hostinger) serves those directly with no container at all.
# So this is not required for that deployment path.
#
# It is still worth having, for three reasons:
#
#   1. One command runs the whole system. `docker compose up` starts the
#      backend and the frontend together, configured to talk to each other,
#      with no local Node or Python install needed at all.
#   2. It builds identically everywhere. "It works on my machine" stops being
#      possible, because the machine is described in this file.
#   3. It keeps the hosting decision open. If Hostinger ever stops being the
#      right answer, this image runs on any container platform without change.
#
# The build has two stages: the first compiles the application using Node, the
# second copies only the finished files into a small nginx image. Node, npm and
# the several hundred megabytes of build tooling are left behind — and every
# tool absent from a running image is one an attacker cannot use.
# =====================================================================

# ---------------------------------------------------------------------
# Stage 1: build
# ---------------------------------------------------------------------
FROM node:24-alpine AS builder

WORKDIR /build

# Copy the dependency manifests first, before the source.
#
# Docker caches each step while its inputs are unchanged. Because the source
# changes constantly and the dependency list rarely does, this ordering means
# an ordinary code change reuses the cached install and rebuilds in seconds
# instead of minutes.
COPY package.json package-lock.json ./

# `npm ci` installs exactly what the lock file specifies, rather than
# re-resolving versions the way `npm install` does. In a build you want the
# same result every time, not the newest compatible one.
RUN npm ci

COPY . .

RUN npm run build

# ---------------------------------------------------------------------
# Stage 2: serve
# ---------------------------------------------------------------------
FROM nginx:1.27-alpine

RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/app.conf

# Note the `/browser` on the end. Angular puts the browser bundle in a
# subfolder, and copying the level above it produces a blank page — the single
# most common mistake when deploying this application by hand, too.
COPY --from=builder /build/dist/ai-dungeon-master/browser /usr/share/nginx/html

# Port 8080 rather than 80, so the server can run as a non-root user.
# Ports below 1024 require root on Linux, and running a web server as root
# means a flaw in it hands over the whole container.
EXPOSE 8080

# The nginx image ships an unprivileged user for exactly this.
RUN chown -R nginx:nginx /usr/share/nginx/html \
    && chown -R nginx:nginx /var/cache/nginx \
    && touch /var/run/nginx.pid \
    && chown nginx:nginx /var/run/nginx.pid

USER nginx

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q --spider http://localhost:8080/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
