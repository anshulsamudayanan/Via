# syntax=docker/dockerfile:1
# MinIO for local development, built from official source at a pinned commit.
#
# Why not the official image? MinIO stopped publishing community images to
# Docker Hub, and quay.io may not be reachable from every build environment.
# Building from github.com/minio/minio (via the Go module proxy) keeps the
# server official and pinned. To use a prebuilt image instead, set
# MINIO_IMAGE in .env and remove the `build:` section of the `minio` service.

FROM golang:1.24.7-alpine AS build
ARG MINIO_VERSION=v0.0.0-20260212201848-7aac2a2c5b7c
# Optional build secret `build_ca`: extra CA bundle for TLS-intercepting proxies.
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export SSL_CERT_FILE=/run/secrets/build_ca; fi; \
    CGO_ENABLED=0 GOBIN=/out go install -trimpath -ldflags "-s -w" "github.com/minio/minio@${MINIO_VERSION}"

FROM alpine:3.22.2
RUN addgroup -S minio && adduser -S minio -G minio && mkdir /data && chown minio:minio /data
COPY --from=build /out/minio /usr/local/bin/minio
USER minio
EXPOSE 9000 9001
HEALTHCHECK --interval=5s --timeout=3s --retries=10 \
  CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:9000/minio/health/live"]
ENTRYPOINT ["minio"]
CMD ["server", "/data", "--address", ":9000", "--console-address", ":9001"]
