# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from django.test import RequestFactory

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.authentication.provider.oauth.dingtalk import DingTalkOAuthProvider, _handa_email_from_name
from plane.db.models import Account, DingTalkDepartment, DingTalkUser, DingTalkUserDepartment, User


def _enabled_dingtalk_config(_keys):
    return ("1", "ding-client-id", "ding-client-secret", "1", "")


def _enabled_dingtalk_config_with_redirect(_keys):
    return (
        "1",
        "ding-client-id",
        "ding-client-secret",
        "1",
        "https://plane.example.com/auth/dingtalk/callback/",
    )


def _request():
    return RequestFactory().get("/auth/dingtalk/", HTTP_HOST="localhost:8000")


@pytest.mark.unit
class TestDingTalkOAuthProvider:
    def test_handa_email_from_chinese_name(self):
        assert _handa_email_from_name("王小明") == "wangxiaoming@handa.com"
        assert _handa_email_from_name("张 三") == "zhangsan@handa.com"

    @patch("plane.authentication.provider.oauth.dingtalk.get_configuration_value", side_effect=_enabled_dingtalk_config)
    def test_auth_url_uses_dingtalk_oauth_parameters(self, _config):
        provider = DingTalkOAuthProvider(request=_request(), state="state-123")

        parsed = urlparse(provider.get_auth_url())
        query = parse_qs(parsed.query)

        assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://login.dingtalk.com/oauth2/auth"
        assert query["client_id"] == ["ding-client-id"]
        assert query["response_type"] == ["code"]
        assert query["scope"] == ["openid corpid"]
        assert query["state"] == ["state-123"]
        assert query["redirect_uri"] == ["http://localhost:8000/auth/dingtalk/callback/"]

    @patch(
        "plane.authentication.provider.oauth.dingtalk.get_configuration_value",
        side_effect=_enabled_dingtalk_config_with_redirect,
    )
    def test_auth_url_uses_configured_redirect_uri(self, _config):
        provider = DingTalkOAuthProvider(request=_request(), state="state-123")

        parsed = urlparse(provider.get_auth_url())
        query = parse_qs(parsed.query)

        assert query["redirect_uri"] == ["https://plane.example.com/auth/dingtalk/callback/"]

    @pytest.mark.django_db
    @patch("plane.authentication.provider.oauth.dingtalk.get_configuration_value", side_effect=_enabled_dingtalk_config)
    def test_authenticate_creates_user_account_and_dingtalk_identity_with_handa_email(self, _config):
        provider = DingTalkOAuthProvider(request=_request(), code="auth-code")
        provider.client = Mock()
        provider.client.get_user_access_token.return_value = {
            "accessToken": "user-access-token",
            "refreshToken": "refresh-token",
            "expireIn": 7200,
        }
        provider.client.get_me.return_value = {
            "unionId": "union-1",
            "openId": "open-1",
            "corpId": "corp-1",
            "nick": "王小明",
            "mobile": "13800000000",
        }
        provider.client.get_org_access_token.return_value = {"accessToken": "org-access-token"}
        provider.client.get_user_id_by_union_id.return_value = {"userid": "user-1"}
        provider.client.get_user_detail.return_value = {
            "userid": "user-1",
            "unionid": "union-1",
            "name": "王小明",
            "mobile": "13800000000",
            "title": "研发",
            "dept_id_list": [10],
            "main_dept_id": 10,
        }
        provider.client.get_department_detail.return_value = {
            "dept_id": 10,
            "parent_id": 1,
            "name": "研发部",
        }

        user = provider.authenticate()

        assert user.email == "wangxiaoming@handa.com"
        assert user.mobile_number == "13800000000"
        assert user.is_password_autoset is True
        assert Account.objects.filter(provider="dingtalk", provider_account_id="corp-1:union-1", user=user).exists()

        dingtalk_user = DingTalkUser.objects.get(corp_id="corp-1", union_id="union-1")
        assert dingtalk_user.user == user
        assert dingtalk_user.dingtalk_user_id == "user-1"
        assert dingtalk_user.mobile == "13800000000"
        assert dingtalk_user.title == "研发"

        department = DingTalkDepartment.objects.get(corp_id="corp-1", dept_id="10")
        assert department.name == "研发部"
        assert DingTalkUserDepartment.objects.filter(
            dingtalk_user=dingtalk_user,
            department=department,
            is_primary=True,
        ).exists()

    @pytest.mark.django_db
    @patch("plane.authentication.provider.oauth.dingtalk.get_configuration_value", side_effect=_enabled_dingtalk_config)
    def test_authenticate_reuses_existing_dingtalk_identity(self, _config):
        existing_user = User.objects.create(
            email="existing@plane.so",
            username="existing-user",
            mobile_number="13800000001",
        )
        DingTalkUser.objects.create(
            user=existing_user,
            corp_id="corp-1",
            union_id="union-1",
            name="Existing",
        )

        provider = DingTalkOAuthProvider(request=_request(), code="auth-code")
        provider.client = Mock()
        provider.client.get_user_access_token.return_value = {"accessToken": "user-access-token", "expireIn": 7200}
        provider.client.get_me.return_value = {
            "unionId": "union-1",
            "openId": "open-1",
            "corpId": "corp-1",
            "nick": "王小明",
            "email": "changed@plane.so",
        }
        provider.client.get_org_access_token.return_value = {"accessToken": "org-access-token"}
        provider.client.get_user_id_by_union_id.return_value = {"userid": "user-1"}
        provider.client.get_user_detail.return_value = {
            "userid": "user-1",
            "unionid": "union-1",
            "name": "王小明",
            "email": "changed@plane.so",
            "dept_id_list": [],
        }

        user = provider.authenticate()

        assert user.id == existing_user.id
        assert user.email == "wangxiaoming@handa.com"
        assert User.objects.count() == 1
        assert Account.objects.filter(provider="dingtalk", provider_account_id="corp-1:union-1", user=user).count() == 1
        assert DingTalkUser.objects.filter(corp_id="corp-1", union_id="union-1").count() == 1

    @pytest.mark.django_db
    @patch("plane.authentication.provider.oauth.dingtalk.get_configuration_value", side_effect=_enabled_dingtalk_config)
    def test_authenticate_uses_token_corp_id_when_profile_omits_it(self, _config):
        provider = DingTalkOAuthProvider(request=_request(), code="auth-code")
        provider.client = Mock()
        provider.client.get_user_access_token.return_value = {
            "accessToken": "user-access-token",
            "corpId": "corp-from-token",
        }
        provider.client.get_me.return_value = {
            "unionId": "union-from-me",
            "openId": "open-1",
            "nick": "王小明",
        }
        provider.client.get_org_access_token.return_value = {"accessToken": "org-access-token"}
        provider.client.get_user_id_by_union_id.return_value = {"userid": "user-1"}
        provider.client.get_user_detail.return_value = {
            "userid": "user-1",
            "unionid": "union-from-me",
            "name": "王小明",
            "dept_id_list": [],
        }

        user = provider.authenticate()

        assert user.email == "wangxiaoming@handa.com"
        assert Account.objects.filter(
            provider="dingtalk",
            provider_account_id="corp-from-token:union-from-me",
            user=user,
        ).exists()
        assert DingTalkUser.objects.filter(corp_id="corp-from-token", union_id="union-from-me", user=user).exists()

    @pytest.mark.django_db
    @patch("plane.authentication.provider.oauth.dingtalk.get_configuration_value", side_effect=_enabled_dingtalk_config)
    def test_open_id_fallback_is_scoped_by_corp_id(self, _config):
        existing_user = User.objects.create(email="existing@plane.so", username="existing-user")
        Account.objects.create(
            user=existing_user,
            provider="dingtalk",
            provider_account_id="corp-1:open-shared",
            access_token="existing-token",
        )

        provider = DingTalkOAuthProvider(request=_request(), code="auth-code")
        provider.client = Mock()
        provider.client.get_user_access_token.return_value = {"accessToken": "user-access-token"}
        provider.client.get_me.return_value = {
            "openId": "open-shared",
            "corpId": "corp-2",
            "nick": "另一个企业用户",
        }

        user = provider.authenticate()

        assert user.id != existing_user.id
        assert Account.objects.filter(provider="dingtalk", provider_account_id="corp-1:open-shared").count() == 1
        assert Account.objects.filter(provider="dingtalk", provider_account_id="corp-2:open-shared", user=user).exists()
        assert DingTalkUser.objects.filter(corp_id="corp-2", union_id="open-shared", user=user).exists()

    @pytest.mark.django_db
    @patch("plane.authentication.provider.oauth.dingtalk.get_configuration_value", side_effect=_enabled_dingtalk_config)
    def test_contact_sync_failure_does_not_block_login_and_is_recorded(self, _config):
        provider = DingTalkOAuthProvider(request=_request(), code="auth-code")
        provider.client = Mock()
        provider.client.get_user_access_token.return_value = {"accessToken": "user-access-token", "corpId": "corp-1"}
        provider.client.get_me.return_value = {
            "unionId": "union-1",
            "openId": "open-1",
            "nick": "王小明",
        }
        provider.client.get_org_access_token.side_effect = AuthenticationException(
            error_code=AUTHENTICATION_ERROR_CODES["DINGTALK_OAUTH_PROVIDER_ERROR"],
            error_message="DINGTALK_OAUTH_PROVIDER_ERROR",
        )

        user = provider.authenticate()

        account = Account.objects.get(provider="dingtalk", provider_account_id="corp-1:union-1", user=user)
        dingtalk_user = DingTalkUser.objects.get(corp_id="corp-1", union_id="union-1", user=user)
        assert account.metadata["sync_error"] == "DINGTALK_OAUTH_PROVIDER_ERROR"
        assert dingtalk_user.raw_data["sync_error"] == "DINGTALK_OAUTH_PROVIDER_ERROR"

    @pytest.mark.django_db
    @patch("plane.authentication.provider.oauth.dingtalk.get_configuration_value", side_effect=_enabled_dingtalk_config)
    def test_missing_corp_id_rejects_login(self, _config):
        provider = DingTalkOAuthProvider(request=_request(), code="auth-code")
        provider.client = Mock()
        provider.client.get_user_access_token.return_value = {"accessToken": "user-access-token"}
        provider.client.get_me.return_value = {
            "openId": "open-without-corp",
            "nick": "无企业信息用户",
        }

        with pytest.raises(AuthenticationException) as exc:
            provider.authenticate()

        assert exc.value.error_message == "DINGTALK_OAUTH_PROVIDER_ERROR"
        assert User.objects.count() == 0
        assert Account.objects.count() == 0
        assert DingTalkUser.objects.count() == 0

    @pytest.mark.django_db
    @patch("plane.authentication.provider.oauth.dingtalk.get_configuration_value", side_effect=_enabled_dingtalk_config)
    def test_identity_upgrade_from_open_id_to_union_id_reuses_existing_user(self, _config):
        existing_user = User.objects.create(
            email="dingtalk_corp_1_open_upgrade@dingtalk.local",
            username="existing-openid-user",
        )
        Account.objects.create(
            user=existing_user,
            provider="dingtalk",
            provider_account_id="corp-1:open-upgrade",
            access_token="existing-token",
        )
        DingTalkUser.objects.create(
            user=existing_user,
            corp_id="corp-1",
            union_id="open-upgrade",
            open_id="open-upgrade",
            name="Existing OpenID User",
        )

        provider = DingTalkOAuthProvider(request=_request(), code="auth-code")
        provider.client = Mock()
        provider.client.get_user_access_token.return_value = {"accessToken": "user-access-token"}
        provider.client.get_me.return_value = {
            "unionId": "union-upgrade",
            "openId": "open-upgrade",
            "corpId": "corp-1",
            "nick": "升级用户",
        }
        provider.client.get_org_access_token.return_value = {"accessToken": "org-access-token"}
        provider.client.get_user_id_by_union_id.return_value = {"userid": "user-upgrade"}
        provider.client.get_user_detail.return_value = {
            "userid": "user-upgrade",
            "unionid": "union-upgrade",
            "name": "升级用户",
            "dept_id_list": [],
        }

        user = provider.authenticate()

        assert user.id == existing_user.id
        assert user.email == "shengjiyonghu@handa.com"
        assert User.objects.count() == 1
        assert Account.objects.filter(provider="dingtalk", provider_account_id="corp-1:union-upgrade", user=user).exists()
        assert Account.objects.filter(provider="dingtalk", provider_account_id="corp-1:open-upgrade").count() == 0
        assert DingTalkUser.objects.filter(corp_id="corp-1", union_id="union-upgrade", user=user).count() == 1
        assert DingTalkUser.objects.filter(corp_id="corp-1", union_id="open-upgrade").count() == 0
