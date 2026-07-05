# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.utils import timezone
from django.db.models import Q

from plane.db.models import DingTalkDepartment, DingTalkUser, DingTalkUserDepartment


def _identity_query(identity):
    query = Q()
    identity_fields = {
        "union_id": identity.get("union_id"),
        "open_id": identity.get("open_id"),
        "dingtalk_user_id": identity.get("dingtalk_user_id"),
    }
    for field, value in identity_fields.items():
        if value:
            query |= Q(**{field: value})
    return query


def sync_dingtalk_identity(user, identity, departments=None):
    now = timezone.now()
    corp_id = identity.get("corp_id") or ""
    union_id = identity.get("union_id")

    if not corp_id or not union_id:
        return None

    dingtalk_user = DingTalkUser.objects.filter(corp_id=corp_id, union_id=union_id).first()
    if not dingtalk_user:
        identity_query = _identity_query(identity)
        if identity_query:
            dingtalk_user = DingTalkUser.objects.filter(corp_id=corp_id).filter(identity_query).first()

    defaults = {
            "user": user,
            "open_id": identity.get("open_id"),
            "dingtalk_user_id": identity.get("dingtalk_user_id"),
            "name": identity.get("name") or identity.get("nick") or "",
            "nick": identity.get("nick"),
            "mobile": identity.get("mobile"),
            "email": identity.get("email"),
            "avatar_url": identity.get("avatar_url"),
            "title": identity.get("title"),
            "raw_data": identity.get("raw_data") or {},
            "last_synced_at": now,
    }

    if dingtalk_user:
        dingtalk_user.union_id = union_id
        for field, value in defaults.items():
            setattr(dingtalk_user, field, value)
        dingtalk_user.save(update_fields=["union_id", *defaults.keys(), "updated_at"])
    else:
        dingtalk_user = DingTalkUser.objects.create(
            corp_id=corp_id,
            union_id=union_id,
            **defaults,
        )

    for department_data in departments or []:
        dept_id = str(department_data.get("dept_id") or department_data.get("deptId") or "")
        if not dept_id:
            continue

        department, _ = DingTalkDepartment.objects.update_or_create(
            corp_id=corp_id,
            dept_id=dept_id,
            defaults={
                "parent_dept_id": department_data.get("parent_dept_id")
                or department_data.get("parent_id")
                or department_data.get("parentId"),
                "name": department_data.get("name") or f"Department {dept_id}",
                "raw_data": department_data,
                "last_synced_at": now,
                "is_active": True,
            },
        )
        DingTalkUserDepartment.objects.update_or_create(
            dingtalk_user=dingtalk_user,
            department=department,
            defaults={
                "is_primary": bool(department_data.get("is_primary", False)),
                "raw_data": department_data,
            },
        )

    return dingtalk_user
