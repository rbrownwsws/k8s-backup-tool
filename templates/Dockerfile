FROM python:3-alpine3.18 AS prep

# Make sure we have the tools get kubectl and rclone
RUN apk --no-cache add \
        ca-certificates \
        curl \
        unzip

WORKDIR /tools

# Expose buildkit target platform args
ARG TARGETOS
ARG TARGETARCH

ARG TARGETK8S

# Environment variables we will use to select kubectl and rclone downloads
ENV TARGETOS=${TARGETOS:-linux}
ENV TARGETARCH=${TARGETARCH:-amd64}
ENV TARGETK8S=${TARGETK8S:-1.27}

# Generate build vars
COPY constants.py .
COPY generate_build_env.py .
COPY requirements.txt .
COPY build_config.yaml .
RUN pip install -r requirements.txt \
    && python3 generate_build_env.py

# Get rclone
RUN source .env \
    && export RCLONE_ARCHIVE=rclone-${RCLONE_VERSION}-${TARGETOS}-${TARGETARCH} \
    && curl -O https://downloads.rclone.org/${RCLONE_VERSION}/${RCLONE_ARCHIVE}.zip \
    && echo "${RCLONE_SHA256}  ${RCLONE_ARCHIVE}.zip" | sha256sum -c - \
    && unzip ${RCLONE_ARCHIVE}.zip \
    && cp ${RCLONE_ARCHIVE}/rclone . \
    && chmod +x ./rclone \
    && rm ${RCLONE_ARCHIVE}.zip \
    && rm -rf ${RCLONE_ARCHIVE}

# Get kubectl
RUN source .env \
    && curl -LO "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/${TARGETOS}/${TARGETARCH}/kubectl" \
    && echo "${KUBECTL_SHA256}  kubectl" | sha256sum -c \
    && chmod +x ./kubectl

FROM alpine:{$ alpine_version $}
RUN apk --no-cache add ca-certificates
COPY --from=prep /tools/rclone /usr/local/bin/rclone
COPY --from=prep /tools/kubectl /usr/local/bin/kubectl
