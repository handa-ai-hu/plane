# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.conf import settings
from django.db import models
from django.utils import timezone

from .base import BaseModel


class DingTalkDepartment(BaseModel):
    corp_id = models.CharField(max_length=255, default="", blank=True, db_index=True)
    dept_id = models.CharField(max_length=255, db_index=True)
    parent_dept_id = models.CharField(max_length=255, null=True, blank=True)
    name = models.CharField(max_length=255)
    raw_data = models.JSONField(default=dict)
    last_synced_at = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "DingTalk Department"
        verbose_name_plural = "DingTalk Departments"
        db_table = "dingtalk_departments"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["corp_id", "dept_id"],
                condition=models.Q(deleted_at__isnull=True),
                name="dingtalk_department_unique_corp_dept_when_deleted_at_null",
            )
        ]

    def __str__(self):
        return f"{self.name} <{self.corp_id}:{self.dept_id}>"


class DingTalkUser(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dingtalk_users",
    )
    corp_id = models.CharField(max_length=255, default="", blank=True, db_index=True)
    union_id = models.CharField(max_length=255, db_index=True)
    open_id = models.CharField(max_length=255, null=True, blank=True)
    dingtalk_user_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    name = models.CharField(max_length=255, blank=True)
    nick = models.CharField(max_length=255, null=True, blank=True)
    mobile = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    email = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    avatar_url = models.TextField(null=True, blank=True)
    title = models.CharField(max_length=255, null=True, blank=True)
    raw_data = models.JSONField(default=dict)
    last_synced_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "DingTalk User"
        verbose_name_plural = "DingTalk Users"
        db_table = "dingtalk_users"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["corp_id", "union_id"],
                condition=models.Q(deleted_at__isnull=True),
                name="dingtalk_user_unique_corp_union_when_deleted_at_null",
            )
        ]

    def __str__(self):
        return f"{self.name or self.union_id} <{self.corp_id}>"


class DingTalkUserDepartment(BaseModel):
    dingtalk_user = models.ForeignKey(
        DingTalkUser,
        on_delete=models.CASCADE,
        related_name="department_links",
    )
    department = models.ForeignKey(
        DingTalkDepartment,
        on_delete=models.CASCADE,
        related_name="user_links",
    )
    is_primary = models.BooleanField(default=False)
    raw_data = models.JSONField(default=dict)

    class Meta:
        verbose_name = "DingTalk User Department"
        verbose_name_plural = "DingTalk User Departments"
        db_table = "dingtalk_user_departments"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["dingtalk_user", "department"],
                condition=models.Q(deleted_at__isnull=True),
                name="dingtalk_user_department_unique_user_dept_when_deleted_at_null",
            )
        ]

    def __str__(self):
        return f"{self.dingtalk_user_id} <{self.department_id}>"
