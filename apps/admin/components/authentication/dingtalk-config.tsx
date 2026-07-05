/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import Link from "next/link";
// icons
import { Settings2 } from "lucide-react";
// plane internal packages
import { getButtonStyling } from "@plane/propel/button";
import type { TInstanceAuthenticationMethodKeys } from "@plane/types";
import { ToggleSwitch } from "@plane/ui";
import { cn } from "@plane/utils";
// hooks
import { useInstance } from "@/hooks/store";

type Props = {
  disabled: boolean;
  updateConfig: (key: TInstanceAuthenticationMethodKeys, value: string) => void;
};

export const DingTalkConfiguration = observer(function DingTalkConfiguration(props: Props) {
  const { disabled, updateConfig } = props;
  // store
  const { formattedConfig } = useInstance();
  // derived values
  const enableDingTalkConfig = formattedConfig?.IS_DINGTALK_ENABLED ?? "";
  const isDingTalkConfigured = !!formattedConfig?.DINGTALK_CLIENT_ID && !!formattedConfig?.DINGTALK_CLIENT_SECRET;

  return (
    <>
      {isDingTalkConfigured ? (
        <div className="flex items-center gap-4">
          <Link href="/authentication/dingtalk" className={cn(getButtonStyling("link", "base"), "font-medium")}>
            Edit
          </Link>
          <ToggleSwitch
            value={Boolean(parseInt(enableDingTalkConfig))}
            onChange={() => {
              const newEnableDingTalkConfig = Boolean(parseInt(enableDingTalkConfig)) === true ? "0" : "1";
              updateConfig("IS_DINGTALK_ENABLED", newEnableDingTalkConfig);
            }}
            size="sm"
            disabled={disabled}
          />
        </div>
      ) : (
        <Link href="/authentication/dingtalk" className={cn(getButtonStyling("secondary", "base"), "text-tertiary")}>
          <Settings2 className="h-4 w-4 p-0.5 text-tertiary" />
          Configure
        </Link>
      )}
    </>
  );
});
