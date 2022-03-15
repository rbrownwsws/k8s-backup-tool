FROM alpine:3.15 AS prep
RUN apk --no-cache add \
        ca-certificates \
        curl \
        unzip
WORKDIR /tools

    # Get rclone
RUN curl -O https://downloads.rclone.org/rclone-current-linux-amd64.zip \
    && unzip rclone-current-linux-amd64.zip \
    && cp rclone-*-linux-amd64/rclone . \
    # Get kubectl
    && curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && curl -LO "https://dl.k8s.io/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl.sha256" \
    && echo "$(cat kubectl.sha256)  kubectl" | sha256sum -c


FROM alpine:3.15
RUN apk --no-cache add ca-certificates
COPY --from=prep /tools/rclone /usr/local/bin/rclone
RUN chmod +x /usr/local/bin/rclone
COPY --from=prep /tools/kubectl /usr/local/bin/kubectl
RUN chmod +x /usr/local/bin/kubectl