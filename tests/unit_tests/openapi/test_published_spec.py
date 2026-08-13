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
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

from superset.utils import json

REPO_ROOT = Path(__file__).parents[3]
SPEC_PATH = REPO_ROOT / "docs" / "static" / "resources" / "openapi.json"
FIXER_PATH = REPO_ROOT / "docs" / "scripts" / "fix-openapi-spec.py"


def _load_fixer() -> ModuleType:
    """Import the standalone docs script, whose filename isn't importable."""
    spec = importlib.util.spec_from_file_location("fix_openapi_spec", FIXER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_spec() -> dict[str, Any]:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def test_fix_collection_relationship_refs() -> None:
    fixer = _load_fixer()
    spec = {
        "components": {
            "schemas": {
                "DashboardRestApi.get_list": {
                    "properties": {
                        # to-many relationship documented as a single object
                        "owners": {"$ref": "#/components/schemas/User"},
                        # to-one relationship, must be left alone
                        "changed_by": {"$ref": "#/components/schemas/User"},
                        # already correct, must stay untouched
                        "roles": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/Role"},
                        },
                    }
                },
                # hand-written schemas aren't affected by the FAB quirk
                "DashboardGetResponseSchema": {
                    "properties": {"owners": {"$ref": "#/components/schemas/User"}}
                },
            }
        }
    }

    assert fixer.fix_collection_relationship_refs(spec) == 1

    schemas = spec["components"]["schemas"]
    properties = schemas["DashboardRestApi.get_list"]["properties"]
    assert properties["owners"] == {
        "type": "array",
        "items": {"$ref": "#/components/schemas/User"},
    }
    assert properties["changed_by"] == {"$ref": "#/components/schemas/User"}
    assert properties["roles"] == {
        "type": "array",
        "items": {"$ref": "#/components/schemas/Role"},
    }
    assert schemas["DashboardGetResponseSchema"]["properties"]["owners"] == {
        "$ref": "#/components/schemas/User"
    }

    # running the fixer again is a no-op
    assert fixer.fix_collection_relationship_refs(spec) == 0


def test_published_spec_documents_collections_as_arrays() -> None:
    """The published spec must not describe a to-many relationship as an object.

    Generated clients break at runtime when e.g. ``owners`` is declared as a
    single user object but the API returns a list of them.
    """
    fixer = _load_fixer()

    assert fixer.fix_collection_relationship_refs(_load_spec()) == 0
