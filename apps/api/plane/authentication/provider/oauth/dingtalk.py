# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import os
import re
import uuid
from datetime import timedelta
from urllib.parse import urlencode, urlparse

import pytz
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from pypinyin import lazy_pinyin

from plane.authentication.adapter.error import (
    AUTHENTICATION_ERROR_CODES,
    AuthenticationException,
)
from plane.authentication.adapter.oauth import OauthAdapter
from plane.db.models import Account, DingTalkUser, Profile, User
from plane.integrations.dingtalk.client import DingTalkClient
from plane.integrations.dingtalk.sync import sync_dingtalk_identity
from plane.license.utils.instance_value import get_configuration_value

DINGTALK_EMAIL_DOMAIN = "handa.com"


def _first_value(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _safe_email_part(value):
    value = re.sub(r"[^a-zA-Z0-9]+", "_", str(value or "unknown")).strip("_").lower()
    return (value or "unknown")[:80]


def _safe_account_part(value):
    value = re.sub(r"[:\s]+", "_", str(value or "unknown")).strip("_")
    return (value or "unknown")[:120]


def _ascii_email_part(value):
    return re.sub(r"[^a-zA-Z0-9]+", "", str(value or ""))


def _handa_email_from_name(name):
    name = str(name or "").strip()
    if not name:
        return None

    local_part = "".join(lazy_pinyin(name, errors=_ascii_email_part))
    local_part = re.sub(r"[^a-zA-Z0-9]+", "", local_part).lower()
    if not local_part:
        return None
    return f"{local_part[:80]}@{DINGTALK_EMAIL_DOMAIN}"


def _build_redirect_uri(request, configured_redirect_uri=None):
    if configured_redirect_uri:
        redirect_uri = str(configured_redirect_uri).strip()
        parsed_uri = urlparse(redirect_uri)
        if parsed_uri.scheme in ("http", "https") and parsed_uri.netloc:
            return redirect_uri

        raise AuthenticationException(
            error_code=AUTHENTICATION_ERROR_CODES["DINGTALK_NOT_CONFIGURED"],
            error_message="DINGTALK_REDIRECT_URI_INVALID",
        )

    return f"{'https' if request.is_secure() else 'http'}://{request.get_host()}/auth/dingtalk/callback/"


class DingTalkOAuthProvider(OauthAdapter):
    provider = "dingtalk"
    scope = "openid corpid"

    def __init__(self, request, code=None, state=None, callback=None):
        (
            IS_DINGTALK_ENABLED,
            DINGTALK_CLIENT_ID,
            DINGTALK_CLIENT_SECRET,
            ENABLE_DINGTALK_CONTACT_SYNC,
            DINGTALK_REDIRECT_URI,
        ) = get_configuration_value(
            [
                {
                    "key": "IS_DINGTALK_ENABLED",
                    "default": os.environ.get("IS_DINGTALK_ENABLED", "0"),
                },
                {
                    "key": "DINGTALK_CLIENT_ID",
                    "default": os.environ.get("DINGTALK_CLIENT_ID"),
                },
                {
                    "key": "DINGTALK_CLIENT_SECRET",
                    "default": os.environ.get("DINGTALK_CLIENT_SECRET"),
                },
                {
                    "key": "ENABLE_DINGTALK_CONTACT_SYNC",
                    "default": os.environ.get("ENABLE_DINGTALK_CONTACT_SYNC", "1"),
                },
                {
                    "key": "DINGTALK_REDIRECT_URI",
                    "default": os.environ.get("DINGTALK_REDIRECT_URI", ""),
                },
            ]
        )

        if IS_DINGTALK_ENABLED != "1" or not (DINGTALK_CLIENT_ID and DINGTALK_CLIENT_SECRET):
            raise AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["DINGTALK_NOT_CONFIGURED"],
                error_message="DINGTALK_NOT_CONFIGURED",
            )

        self.client = DingTalkClient(client_id=DINGTALK_CLIENT_ID, client_secret=DINGTALK_CLIENT_SECRET)
        self.contact_sync_enabled = ENABLE_DINGTALK_CONTACT_SYNC == "1"
        self.dingtalk_identity = {}
        self.dingtalk_departments = []
        self.dingtalk_sync_error = None

        redirect_uri = _build_redirect_uri(request=request, configured_redirect_uri=DINGTALK_REDIRECT_URI)
        url_params = {
            "client_id": DINGTALK_CLIENT_ID,
            "scope": self.scope,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "prompt": "consent",
        }
        auth_url = f"{DingTalkClient.authorize_url}?{urlencode(url_params)}"

        super().__init__(
            request,
            self.provider,
            DINGTALK_CLIENT_ID,
            self.scope,
            redirect_uri,
            auth_url,
            DingTalkClient.user_access_token_url,
            DingTalkClient.me_url,
            DINGTALK_CLIENT_SECRET,
            code,
            callback=callback,
        )

    def _raise_provider_error(self):
        raise AuthenticationException(
            error_code=AUTHENTICATION_ERROR_CODES["DINGTALK_OAUTH_PROVIDER_ERROR"],
            error_message="DINGTALK_OAUTH_PROVIDER_ERROR",
        )

    def _expires_at(self, response):
        expires_in = _first_value(response.get("expireIn"), response.get("expiresIn"), response.get("expires_in"))
        if not expires_in:
            return None
        try:
            return timezone.now().astimezone(pytz.utc) + timedelta(seconds=int(expires_in))
        except (TypeError, ValueError):
            return None

    def set_token_data(self):
        token_response = self.client.get_user_access_token(code=self.code)
        access_token = token_response.get("accessToken") or token_response.get("access_token")
        if not access_token:
            self._raise_provider_error()

        super().set_token_data(
            {
                "access_token": access_token,
                "refresh_token": token_response.get("refreshToken") or token_response.get("refresh_token"),
                "access_token_expired_at": self._expires_at(token_response),
                "refresh_token_expired_at": None,
                "id_token": "",
                "corp_id": _first_value(
                    token_response.get("corpId"),
                    token_response.get("corp_id"),
                    token_response.get("corpID"),
                )
                or "",
            }
        )

    def _placeholder_email(self, corp_id, provider_id):
        return f"dingtalk_{_safe_email_part(corp_id)}_{_safe_email_part(provider_id)}@dingtalk.local"

    def _fetch_org_profile(self, me_response):
        union_id = _first_value(me_response.get("unionId"), me_response.get("unionid"))
        user_id = _first_value(me_response.get("userId"), me_response.get("userid"))
        if not self.contact_sync_enabled or not (union_id or user_id):
            return {}, []

        try:
            org_token_response = self.client.get_org_access_token()
            org_access_token = org_token_response.get("accessToken") or org_token_response.get("access_token")
            if not org_access_token:
                self._raise_provider_error()

            if not user_id and union_id:
                union_response = self.client.get_user_id_by_union_id(
                    org_access_token=org_access_token,
                    union_id=union_id,
                )
                user_id = _first_value(union_response.get("userid"), union_response.get("userId"))

            if not user_id:
                return {}, []

            user_detail = self.client.get_user_detail(org_access_token=org_access_token, user_id=user_id)
            dept_ids = user_detail.get("dept_id_list") or user_detail.get("deptIdList") or []
            primary_dept_id = _first_value(user_detail.get("main_dept_id"), user_detail.get("mainDeptId"))
            departments = []
            for dept_id in dept_ids:
                try:
                    department = self.client.get_department_detail(org_access_token=org_access_token, dept_id=dept_id)
                except AuthenticationException:
                    department = {}
                department["dept_id"] = str(_first_value(department.get("dept_id"), department.get("deptId"), dept_id))
                department["is_primary"] = str(dept_id) == str(primary_dept_id) if primary_dept_id else False
                departments.append(department)
            return user_detail, departments
        except AuthenticationException as exc:
            self.dingtalk_sync_error = exc.error_message
            return {}, []

    def _build_identity(self, me_response, user_detail):
        union_id = _first_value(
            user_detail.get("unionid"),
            user_detail.get("unionId"),
            me_response.get("unionId"),
            me_response.get("unionid"),
        )
        open_id = _first_value(me_response.get("openId"), me_response.get("openid"))
        dingtalk_user_id = _first_value(
            user_detail.get("userid"),
            user_detail.get("userId"),
            me_response.get("userId"),
            me_response.get("userid"),
        )
        provider_id = _first_value(union_id, open_id, dingtalk_user_id)
        if not provider_id:
            self._raise_provider_error()

        corp_id = _first_value(
            me_response.get("corpId"),
            me_response.get("corp_id"),
            user_detail.get("corpId"),
            user_detail.get("corp_id"),
            self.token_data.get("corp_id") if self.token_data else None,
            "",
        )
        if not corp_id:
            self._raise_provider_error()

        name = _first_value(user_detail.get("name"), me_response.get("name"), me_response.get("nick"), "")
        email = _handa_email_from_name(name)
        if not email:
            email = _first_value(user_detail.get("email"), me_response.get("email"))
        if not email:
            email = self._placeholder_email(corp_id=corp_id, provider_id=provider_id)

        nick = _first_value(me_response.get("nick"), user_detail.get("nick"))
        identity = {
            "corp_id": corp_id or "",
            "union_id": union_id or provider_id,
            "open_id": open_id,
            "dingtalk_user_id": dingtalk_user_id,
            "provider_id": provider_id,
            "email": email,
            "mobile": _first_value(user_detail.get("mobile"), me_response.get("mobile")),
            "name": name,
            "nick": nick,
            "avatar_url": _first_value(user_detail.get("avatar"), me_response.get("avatarUrl"), me_response.get("avatar")),
            "title": user_detail.get("title"),
            "raw_data": {
                "me": me_response,
                "user_detail": user_detail,
                "sync_error": self.dingtalk_sync_error,
            },
        }
        return identity

    def _account_provider_id_for(self, provider_id):
        return "%s:%s" % (
            _safe_account_part(self.dingtalk_identity.get("corp_id")),
            _safe_account_part(provider_id),
        )

    def _account_provider_id(self):
        return self._account_provider_id_for(self.dingtalk_identity.get("provider_id"))

    def _account_provider_ids(self):
        provider_ids = [
            self.dingtalk_identity.get("provider_id"),
            self.dingtalk_identity.get("union_id"),
            self.dingtalk_identity.get("open_id"),
            self.dingtalk_identity.get("dingtalk_user_id"),
        ]
        account_provider_ids = []
        for provider_id in provider_ids:
            if not provider_id:
                continue
            account_provider_id = self._account_provider_id_for(provider_id)
            if account_provider_id not in account_provider_ids:
                account_provider_ids.append(account_provider_id)
        return account_provider_ids

    def _dingtalk_user_identity_query(self):
        query = Q()
        identity_fields = {
            "union_id": self.dingtalk_identity.get("union_id"),
            "open_id": self.dingtalk_identity.get("open_id"),
            "dingtalk_user_id": self.dingtalk_identity.get("dingtalk_user_id"),
        }
        for field, value in identity_fields.items():
            if value:
                query |= Q(**{field: value})
        return query

    def set_user_data(self):
        me_response = self.client.get_me(user_access_token=self.token_data.get("access_token"))
        user_detail, departments = self._fetch_org_profile(me_response=me_response)
        identity = self._build_identity(me_response=me_response, user_detail=user_detail)
        self.dingtalk_identity = identity
        self.dingtalk_departments = departments

        super().set_user_data(
            {
                "email": identity.get("email"),
                "user": {
                    "provider_id": identity.get("provider_id"),
                    "avatar": identity.get("avatar_url") or "",
                    "first_name": identity.get("name")
                    or identity.get("nick")
                    or User.get_display_name(identity.get("email")),
                    "last_name": "",
                    "display_name": identity.get("name") or identity.get("nick"),
                    "is_password_autoset": True,
                    "mobile": identity.get("mobile"),
                },
            }
        )

    def _resolve_existing_user(self, email, mobile):
        candidates = []

        dingtalk_identity_query = self._dingtalk_user_identity_query()
        if dingtalk_identity_query:
            dingtalk_users = DingTalkUser.objects.filter(
                corp_id=self.dingtalk_identity.get("corp_id") or "",
            ).filter(dingtalk_identity_query).select_related("user")
            candidates.extend([dingtalk_user.user for dingtalk_user in dingtalk_users])

        accounts = Account.objects.filter(
            provider=self.provider,
            provider_account_id__in=self._account_provider_ids(),
        ).select_related("user")
        candidates.extend([account.user for account in accounts])

        email_user = User.objects.filter(email=email).first()
        if email_user:
            candidates.append(email_user)

        if mobile:
            mobile_user = User.objects.filter(mobile_number=mobile).first()
            if mobile_user:
                candidates.append(mobile_user)

        unique_candidates = {candidate.id: candidate for candidate in candidates if candidate}
        if len(unique_candidates) > 1:
            self._raise_provider_error()
        return next(iter(unique_candidates.values()), None)

    def _sync_user_email(self, user, email):
        if not email or user.email == email:
            return user

        if User.objects.filter(email=email).exclude(id=user.id).exists():
            self._raise_provider_error()

        user.email = email
        user.is_email_verified = True
        user.save(update_fields=["email", "is_email_verified", "updated_at"])
        return user

    def create_update_account(self, user):
        account_provider_id = self._account_provider_id()
        accounts = list(Account.objects.filter(
            provider=self.provider,
            provider_account_id__in=self._account_provider_ids(),
        ))
        if any(account.user_id != user.id for account in accounts):
            self._raise_provider_error()

        account = next(
            (account for account in accounts if account.provider_account_id == account_provider_id),
            accounts[0] if accounts else None,
        )
        metadata = {
            "corp_id": self.dingtalk_identity.get("corp_id"),
            "union_id": self.dingtalk_identity.get("union_id"),
            "open_id": self.dingtalk_identity.get("open_id"),
            "dingtalk_user_id": self.dingtalk_identity.get("dingtalk_user_id"),
            "provider_id": self.dingtalk_identity.get("provider_id"),
            "sync_error": self.dingtalk_sync_error,
        }

        if account:
            account.user = user
            account.provider_account_id = account_provider_id
            account.access_token = self.token_data.get("access_token")
            account.refresh_token = self.token_data.get("refresh_token")
            account.access_token_expired_at = self.token_data.get("access_token_expired_at")
            account.refresh_token_expired_at = self.token_data.get("refresh_token_expired_at")
            account.last_connected_at = timezone.now()
            account.id_token = self.token_data.get("id_token", "")
            account.metadata = metadata
            account.save()
        else:
            Account.objects.create(
                user=user,
                provider=self.provider,
                provider_account_id=account_provider_id,
                access_token=self.token_data.get("access_token"),
                refresh_token=self.token_data.get("refresh_token"),
                access_token_expired_at=self.token_data.get("access_token_expired_at"),
                refresh_token_expired_at=self.token_data.get("refresh_token_expired_at"),
                last_connected_at=timezone.now(),
                id_token=self.token_data.get("id_token", ""),
                metadata=metadata,
            )

    def complete_login_or_signup(self):
        email = self.sanitize_email(self.user_data.get("email"))
        mobile = self.user_data.get("user", {}).get("mobile")

        with transaction.atomic():
            user = self._resolve_existing_user(email=email, mobile=mobile)

            if user and not user.is_active and user.last_logout_time is not None:
                raise AuthenticationException(
                    error_code=AUTHENTICATION_ERROR_CODES["USER_ACCOUNT_DEACTIVATED"],
                    error_message="USER_ACCOUNT_DEACTIVATED",
                    payload={"email": email},
                )

            is_signup = not bool(user)
            if not user:
                self._Adapter__check_signup(email)
                user = User(email=email, username=uuid.uuid4().hex)
                user.set_password(uuid.uuid4().hex)
                user.is_password_autoset = True
                user.is_email_verified = True
                user.first_name = self.user_data.get("user", {}).get("first_name") or ""
                user.last_name = ""
                user.display_name = self.user_data.get("user", {}).get("display_name") or User.get_display_name(email)
                user.mobile_number = mobile
                user.save()
                Profile.objects.get_or_create(user=user)
            else:
                sync_enabled = self.check_sync_enabled()
                if sync_enabled:
                    user = self.sync_user_data(user=user)
                    user = self._sync_user_email(user=user, email=email)
                if mobile and (sync_enabled or not user.mobile_number) and user.mobile_number != mobile:
                    user.mobile_number = mobile
                    user.save(update_fields=["mobile_number"])

            user = self.save_user_data(user=user)

            if self.callback:
                self.callback(user, is_signup, self.request)

            self.create_update_account(user=user)
            sync_dingtalk_identity(
                user=user,
                identity=self.dingtalk_identity,
                departments=self.dingtalk_departments,
            )

        return user
