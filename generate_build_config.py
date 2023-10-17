import subprocess
import re
import requests
import semver
import yaml

from constants import *
from jinja2 import Environment, FileSystemLoader, select_autoescape


def get_docker_tags(namespace: str, repository: str) -> list[str]:
    response = requests.get(f"https://hub.docker.com/v2/namespaces/{namespace}/repositories/{repository}/tags")
    if response.status_code != 200:
        raise Exception(
            f"Failed to get tags for docker repo {namespace}/{repository}"
        )
    tag_results = response.json()["results"]
    tags = []
    for tag_info in tag_results:
        tags.append(tag_info["name"])
    return tags


def get_git_tags(repo_url: str) -> list[str]:
    # Call the git command to get a raw list of tags.
    cmd_result = subprocess.run(
        ["git", "ls-remote", "--tags", "--refs", repo_url],
        capture_output=True,
        text=True,
    )
    if cmd_result.returncode != 0:
        raise Exception("Failed to get tags")
    out_lines = cmd_result.stdout.splitlines()

    # Strip unneeded info to get just the tag names.
    strip_regex = re.compile(r"^[0-9a-f]+\s+refs/tags/")
    tags = []
    for line in out_lines:
        tag = re.sub(strip_regex, "", line)
        tags.append(tag)

    return tags


def tags_to_versions(version_regex: re.Pattern[str], tags: list[str]) -> list[semver.Version]:
    versions = []
    for tag in tags:
        match = re.match(version_regex, tag)
        if match is not None:
            versions.append(semver.Version.parse(match.group(1)))

    return versions


def get_alpine_versions() -> list[semver.Version]:
    tags = get_docker_tags(namespace="library", repository="alpine")
    version_regex = re.compile(r"^(\d+\.\d+\.\d+)$")
    return tags_to_versions(version_regex, tags)


def get_kubectl_versions() -> list[semver.Version]:
    tags = get_git_tags("https://github.com/kubernetes/kubectl.git")
    version_regex = re.compile(r"^kubernetes-(\d+\.\d+\.\d+)$")
    return tags_to_versions(version_regex, tags)


def get_rclone_versions() -> list[semver.Version]:
    tags = get_git_tags("https://github.com/rclone/rclone")
    version_regex = re.compile(r"^v(\d+\.\d+\.\d+)$")
    return tags_to_versions(version_regex, tags)


# Get the available versions of the software we want to use.
print("Getting alpine versions")
all_alpine_versions = get_alpine_versions()
latest_alpine_version = max(all_alpine_versions)

print("Getting kubectl versions")
all_kubectl_versions = get_kubectl_versions()
latest_kubectl_version = max(all_kubectl_versions)

print("Getting rclone versions")
all_rclone_versions = get_rclone_versions()
latest_rclone_version = max(all_rclone_versions)

# If a major update has come out for one of our dependencies we need to manually check things.
# Just abort this script for safety.
assert latest_alpine_version.major == 3
assert latest_kubectl_version.major == 1
assert latest_rclone_version.major == 1

# Find the corresponding kubectl versions for the versions of Kubernetes we support.
supported_k8s_minor_versions = range(
    latest_kubectl_version.minor - 3, latest_kubectl_version.minor + 1
)
chosen_kubectl_versions = {}
for k8s_minor in supported_k8s_minor_versions:
    # Kubectl can be up to one minor version newer than kube-apiserver.
    # Choose a newer minor version of kubectl if we can.
    kubectl_minor = (
        k8s_minor if k8s_minor == latest_kubectl_version.minor else k8s_minor + 1
    )

    # Find the newest patch version of kubectl for the desired minor version.
    latest_kubectl_for_k8s = max(
        filter(
            lambda v: v.major == 1 and v.minor == kubectl_minor, all_kubectl_versions
        )
    )
    chosen_kubectl_versions[k8s_minor] = latest_kubectl_for_k8s

# Read the current build config so that we can check if anything needs to be changed.
current_build_config = yaml.load(open(CONFIG_FILE, "r"), Loader=yaml.Loader)
config_changed = False

# Start building a new build config.
new_build_config = {}
new_build_config[KEY_RCLONE_VERSION] = f"v{latest_rclone_version}"

new_build_config[KEY_KUBECTL_VERSION] = {}
for k8s_minor, kubectl_version in chosen_kubectl_versions.items():
    new_build_config[KEY_KUBECTL_VERSION][f"1.{k8s_minor}"] = f"v{kubectl_version}"

# Check if the rclone version has changed.
if current_build_config[KEY_RCLONE_VERSION] == new_build_config[KEY_RCLONE_VERSION]:
    print("rclone is up to date.")
    new_build_config[KEY_RCLONE_DOWNLOAD] = current_build_config[KEY_RCLONE_DOWNLOAD]
else:
    print("rclone needs to be updated.")
    config_changed = True
    new_build_config[KEY_RCLONE_DOWNLOAD] = []

    print("Getting checksums for rclone.")
    checksum_req = requests.get(
        f"https://github.com/rclone/rclone/releases/download/{new_build_config[KEY_RCLONE_VERSION]}/SHA256SUMS"
    )
    if checksum_req.status_code != 200:
        raise Exception(f"Failed to get checksum for rclone")

    for arch in SUPPORTED_ARCHES:
        filename = f"rclone-{new_build_config[KEY_RCLONE_VERSION]}-linux-{arch}.zip"
        regex = r"^([0-9a-f]{64})\s+" + re.escape(filename) + r"$"
        m = re.search(regex, checksum_req.text, flags=re.MULTILINE)
        if m is None:
            raise Exception(f"Could not find checksum for {filename}")
        else:
            checksum = m.group(1)
            new_build_config[KEY_RCLONE_DOWNLOAD].append(
                {"arch": arch, "os": "linux", "sha256": checksum}
            )

# Check if the kubectl versions have changed.
if current_build_config[KEY_KUBECTL_VERSION] == new_build_config[KEY_KUBECTL_VERSION]:
    print("kubectl is up to date.")
    new_build_config[KEY_KUBECTL_DOWNLOAD] = current_build_config[KEY_KUBECTL_DOWNLOAD]
else:
    print("kubectl needs to be updated.")
    config_changed = True
    new_build_config[KEY_KUBECTL_DOWNLOAD] = []
    for kubectl_version in sorted(set(new_build_config[KEY_KUBECTL_VERSION].values())):
        for arch in SUPPORTED_ARCHES:
            print(f"Getting checksum for kubectl {kubectl_version} - {arch}")
            checksum_req = requests.get(
                f"https://dl.k8s.io/release/{kubectl_version}/bin/linux/{arch}/kubectl.sha256"
            )
            if checksum_req.status_code != 200:
                raise Exception(
                    f"Failed to get checksum for kubectl {kubectl_version} - {arch}"
                )

            new_build_config[KEY_KUBECTL_DOWNLOAD].append(
                {
                    "arch": arch,
                    "os": "linux",
                    "version": kubectl_version,
                    "sha256": checksum_req.text,
                }
            )

print(f"Updating build config file")
yaml.dump(new_build_config, open(CONFIG_FILE, "w"))

jinja_env = Environment(
    # The variable start/end string must be changed so that it does not conflict with expressions in GitHub actions.
    # e.g. ${{ github.repository }}
    variable_start_string="{$",
    variable_end_string="$}",
    keep_trailing_newline=True,
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape()
)

print("Updating Dockerfile")
dockerfile_template = jinja_env.get_template("Dockerfile")
new_dockerfile = dockerfile_template.render(alpine_version=latest_alpine_version)
with open("Dockerfile", "w") as fh:
    fh.write(new_dockerfile)

print("Updating GitHub CI/CD workflow")
github_action_template = jinja_env.get_template("ci-cd.yaml")
new_ci_cd_workflow = github_action_template.render(k8s_versions=list(new_build_config[KEY_KUBECTL_VERSION].keys()))
with open(".github/workflows/ci-cd.yaml", "w") as fh:
    fh.write(new_ci_cd_workflow)
