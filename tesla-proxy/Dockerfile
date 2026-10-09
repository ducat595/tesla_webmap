# Optional waypoint-capable signing proxy based on upstream PR #443.
# This PR is NOT part of Tesla's official released proxy. No build/vehicle test performed here.
FROM golang:1.26 AS build
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git init && git remote add origin https://github.com/teslamotors/vehicle-command.git && git fetch --depth=1 origin 281b3a70caaef258e2f7dfe0136a2a192b8cb017 && git checkout --detach FETCH_HEAD
RUN CGO_ENABLED=0 go build -o /out/tesla-http-proxy ./cmd/tesla-http-proxy
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/tesla-http-proxy /usr/local/bin/tesla-http-proxy
USER 65532:65532
EXPOSE 4443
ENTRYPOINT ["tesla-http-proxy"]
CMD ["-host","0.0.0.0","-port","4443","-key-file","/config/fleet-key.pem","-tls-key","/config/tls-key.pem","-cert","/config/tls-cert.pem"]
