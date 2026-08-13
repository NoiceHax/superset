# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import re
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[2] / "Dockerfile"

# `FROM <image> AS <stage>`, optionally prefixed with flags such as `--platform`
FROM_PATTERN = re.compile(r"^FROM\s+(?:--\S+\s+)*(\S+)\s+AS\s+(\S+)$", re.IGNORECASE)

# Runtime shared libraries the production images link against. The matching
# `-dev` packages, which provide their headers, must stay out of those images.
RUNTIME_LIBRARIES = {"libecpg6", "libldap2", "libpq5", "libsasl2-2"}


def _instructions(dockerfile: str) -> list[str]:
    """Collapse comments and line continuations into logical instructions."""
    instructions: list[str] = []
    buffer = ""
    for raw_line in dockerfile.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            buffer += f"{line[:-1].strip()} "
            continue
        instructions.append(f"{buffer}{line}")
        buffer = ""
    return instructions


def _installed_packages(stage: str) -> set[str]:
    """Collect the apt packages a stage inherits from its whole `FROM` lineage."""
    parents: dict[str, str] = {}
    packages: dict[str, set[str]] = {}
    current = ""
    for instruction in _instructions(DOCKERFILE.read_text()):
        if match := FROM_PATTERN.match(instruction):
            parent, current = match.groups()
            parents[current] = parent
            packages.setdefault(current, set())
        elif "apt-install.sh" in instruction:
            _, _, args = instruction.partition("apt-install.sh")
            packages.setdefault(current, set()).update(args.split())

    installed: set[str] = set()
    while stage in packages:
        installed |= packages[stage]
        stage = parents[stage]
    return installed


def test_production_images_exclude_development_packages() -> None:
    for stage in ("lean", "ci", "showtime"):
        installed = _installed_packages(stage)
        assert installed, f"no apt packages found for the '{stage}' stage"
        dev_packages = {pkg for pkg in installed if pkg.endswith("-dev")}
        assert not dev_packages, (
            f"the '{stage}' image must not ship development packages: {dev_packages}"
        )


def test_production_images_keep_runtime_shared_libraries() -> None:
    assert RUNTIME_LIBRARIES <= _installed_packages("lean")


def test_dev_image_installs_build_headers() -> None:
    assert {"libldap2-dev", "libsasl2-dev"} <= _installed_packages("dev")
