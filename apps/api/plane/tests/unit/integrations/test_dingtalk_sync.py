# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest

from plane.db.models import DingTalkDepartment, DingTalkUser, DingTalkUserDepartment
from plane.integrations.dingtalk.sync import sync_dingtalk_identity


@pytest.mark.unit
class TestDingTalkSync:
    @pytest.mark.django_db
    def test_sync_dingtalk_identity_is_idempotent(self, create_user):
        identity = {
            "corp_id": "corp-1",
            "union_id": "union-1",
            "open_id": "open-1",
            "dingtalk_user_id": "user-1",
            "name": "王小明",
            "mobile": "13800000000",
            "email": "user@example.com",
            "title": "研发",
            "raw_data": {"source": "test"},
        }
        departments = [{"dept_id": 10, "parent_id": 1, "name": "研发部", "is_primary": True}]

        sync_dingtalk_identity(user=create_user, identity=identity, departments=departments)
        sync_dingtalk_identity(user=create_user, identity=identity, departments=departments)

        dingtalk_user = DingTalkUser.objects.get(corp_id="corp-1", union_id="union-1")
        department = DingTalkDepartment.objects.get(corp_id="corp-1", dept_id="10")

        assert dingtalk_user.user == create_user
        assert DingTalkUser.objects.count() == 1
        assert DingTalkDepartment.objects.count() == 1
        assert DingTalkUserDepartment.objects.filter(dingtalk_user=dingtalk_user, department=department).count() == 1
