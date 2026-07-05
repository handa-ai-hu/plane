# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import requests

from plane.authentication.adapter.error import (
    AUTHENTICATION_ERROR_CODES,
    AuthenticationException,
)


class DingTalkClient:
    authorize_url = "https://login.dingtalk.com/oauth2/auth"
    user_access_token_url = "https://api.dingtalk.com/v1.0/oauth2/userAccessToken"
    org_access_token_url = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
    me_url = "https://api.dingtalk.com/v1.0/contact/users/me"
    get_user_by_union_id_url = "https://oapi.dingtalk.com/topapi/user/getbyunionid"
    user_detail_url = "https://oapi.dingtalk.com/topapi/v2/user/get"
    department_detail_url = "https://oapi.dingtalk.com/topapi/v2/department/get"
    timeout = 10

    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret

    def _raise_provider_error(self):
        raise AuthenticationException(
            error_code=AUTHENTICATION_ERROR_CODES["DINGTALK_OAUTH_PROVIDER_ERROR"],
            error_message="DINGTALK_OAUTH_PROVIDER_ERROR",
        )

    def _check_oapi_response(self, data):
        errcode = data.get("errcode")
        if errcode not in (None, 0, "0"):
            self._raise_provider_error()
        return data.get("result") or {}

    def _post_json(self, url, payload, headers=None, params=None):
        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers or {"Content-Type": "application/json"},
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError):
            self._raise_provider_error()
        return data

    def _get_json(self, url, headers=None):
        try:
            response = requests.get(url, headers=headers or {}, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            self._raise_provider_error()

    def get_user_access_token(self, code):
        return self._post_json(
            self.user_access_token_url,
            {
                "clientId": self.client_id,
                "clientSecret": self.client_secret,
                "code": code,
                "grantType": "authorization_code",
            },
        )

    def get_org_access_token(self):
        return self._post_json(
            self.org_access_token_url,
            {
                "appKey": self.client_id,
                "appSecret": self.client_secret,
            },
        )

    def get_me(self, user_access_token):
        return self._get_json(
            self.me_url,
            headers={"x-acs-dingtalk-access-token": user_access_token},
        )

    def get_user_id_by_union_id(self, org_access_token, union_id):
        data = self._post_json(
            self.get_user_by_union_id_url,
            {"unionid": union_id},
            params={"access_token": org_access_token},
        )
        return self._check_oapi_response(data)

    def get_user_detail(self, org_access_token, user_id):
        data = self._post_json(
            self.user_detail_url,
            {"userid": user_id, "language": "zh_CN"},
            params={"access_token": org_access_token},
        )
        return self._check_oapi_response(data)

    def get_department_detail(self, org_access_token, dept_id):
        data = self._post_json(
            self.department_detail_url,
            {"dept_id": dept_id, "language": "zh_CN"},
            params={"access_token": org_access_token},
        )
        return self._check_oapi_response(data)
