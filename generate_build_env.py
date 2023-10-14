import os
import yaml

from constants import *

target_os = os.environ["TARGETOS"]
target_arch = os.environ["TARGETARCH"]
target_k8s = os.environ["TARGETK8S"]

build_config = yaml.load(open(CONFIG_FILE, "r"), Loader=yaml.Loader)

# Find the version of kubectl we want to use for the given kubernetes version
if target_k8s not in build_config[KEY_KUBECTL_VERSION]:
    print("Unknown kubernetes version: " + target_k8s)
    exit(1)
kubectl_version = build_config[KEY_KUBECTL_VERSION][target_k8s]

# Find the sha256 hash of the kubectl binary
kubectl_sha256 = ""
try:
    kubectl_sha256 = next(
        download["sha256"]
        for download in build_config[KEY_KUBECTL_DOWNLOAD]
        if download["version"] == kubectl_version
        and download["os"] == target_os
        and download["arch"] == target_arch
    )
except StopIteration:
    print(
        f"Could not find kubectl version {kubectl_version} for target {target_os}/{target_arch}"
    )
    exit(1)

rclone_version = build_config[KEY_RCLONE_VERSION]
# Find the sha256 hash of the rclone binary
rclone_sha256 = ""
try:
    rclone_sha256 = next(
        download["sha256"]
        for download in build_config[KEY_RCLONE_DOWNLOAD]
        if download["os"] == target_os and download["arch"] == target_arch
    )
except StopIteration:
    print(
        f"Could not find rclone version {rclone_version} for target  {target_os}/{target_arch}"
    )
    exit(1)

env_file = open(".env", "w")

env_file.write(f"KUBECTL_VERSION={kubectl_version}\n")
env_file.write(f"KUBECTL_SHA256={kubectl_sha256}\n")

env_file.write(f"RCLONE_VERSION={rclone_version}\n")
env_file.write(f"RCLONE_SHA256={rclone_sha256}\n")

env_file.close()
