/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { isEmpty } from "lodash-es";
import Link from "next/link";
import { useForm } from "react-hook-form";
// plane internal packages
import { API_BASE_URL } from "@plane/constants";
import { Button, getButtonStyling } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { IFormattedInstanceConfiguration, TInstanceDingTalkAuthenticationConfigurationKeys } from "@plane/types";
// components
import { CodeBlock } from "@/components/common/code-block";
import { ConfirmDiscardModal } from "@/components/common/confirm-discard-modal";
import type { TControllerInputFormField } from "@/components/common/controller-input";
import { ControllerInput } from "@/components/common/controller-input";
import type { TControllerSwitchFormField } from "@/components/common/controller-switch";
import { ControllerSwitch } from "@/components/common/controller-switch";
import type { TCopyField } from "@/components/common/copy-field";
import { CopyField } from "@/components/common/copy-field";
// hooks
import { useInstance } from "@/hooks/store";

type Props = {
  config: IFormattedInstanceConfiguration;
};

type DingTalkConfigFormValues = Record<TInstanceDingTalkAuthenticationConfigurationKeys, string>;

export function InstanceDingTalkConfigForm(props: Props) {
  const { config } = props;
  // states
  const [isDiscardChangesModalOpen, setIsDiscardChangesModalOpen] = useState(false);
  // store hooks
  const { updateInstanceConfigurations } = useInstance();
  // form data
  const {
    handleSubmit,
    control,
    reset,
    formState: { errors, isDirty, isSubmitting },
  } = useForm<DingTalkConfigFormValues>({
    defaultValues: {
      DINGTALK_CLIENT_ID: config["DINGTALK_CLIENT_ID"],
      DINGTALK_CLIENT_SECRET: config["DINGTALK_CLIENT_SECRET"],
      ENABLE_DINGTALK_SYNC: config["ENABLE_DINGTALK_SYNC"] || "1",
      ENABLE_DINGTALK_CONTACT_SYNC: config["ENABLE_DINGTALK_CONTACT_SYNC"] || "1",
    },
  });

  const originURL = !isEmpty(API_BASE_URL) ? API_BASE_URL : typeof window !== "undefined" ? window.location.origin : "";

  const DINGTALK_FORM_FIELDS: TControllerInputFormField[] = [
    {
      key: "DINGTALK_CLIENT_ID",
      type: "text",
      label: "Client ID",
      description: (
        <>
          Use the client ID from your DingTalk internal app.{" "}
          <a
            tabIndex={-1}
            href="https://open.dingtalk.com/document/orgapp-server/obtain-identity-credentials"
            target="_blank"
            className="text-accent-primary hover:underline"
            rel="noreferrer"
          >
            Learn more
          </a>
        </>
      ),
      placeholder: "dingxxxxxxxxxxxxxxxx",
      error: Boolean(errors.DINGTALK_CLIENT_ID),
      required: true,
    },
    {
      key: "DINGTALK_CLIENT_SECRET",
      type: "password",
      label: "Client secret",
      description: (
        <>
          Use the client secret from the same DingTalk internal app.{" "}
          <a
            tabIndex={-1}
            href="https://open.dingtalk.com/document/orgapp-server/obtain-identity-credentials"
            target="_blank"
            className="text-accent-primary hover:underline"
            rel="noreferrer"
          >
            Learn more
          </a>
        </>
      ),
      placeholder: "ding-client-secret",
      error: Boolean(errors.DINGTALK_CLIENT_SECRET),
      required: true,
    },
  ];

  const DINGTALK_FORM_SWITCH_FIELDS: TControllerSwitchFormField<DingTalkConfigFormValues>[] = [
    {
      name: "ENABLE_DINGTALK_SYNC",
      label: "DingTalk",
    },
    {
      name: "ENABLE_DINGTALK_CONTACT_SYNC",
      label: "DingTalk contact details",
    },
  ];

  const DINGTALK_SERVICE_FIELD: TCopyField[] = [
    {
      key: "Callback_URI",
      label: "Callback URI",
      url: `${originURL}/auth/dingtalk/callback/`,
      description: (
        <>
          We will auto-generate this. Paste this into your <CodeBlock darkerShade>Callback URL</CodeBlock> field in
          DingTalk developer settings.
        </>
      ),
    },
  ];

  const onSubmit = async (formData: DingTalkConfigFormValues) => {
    const payload: Partial<DingTalkConfigFormValues> = { ...formData };

    try {
      const response = await updateInstanceConfigurations(payload);
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: "Done!",
        message: "Your DingTalk authentication is configured. You should test it now.",
      });
      reset({
        DINGTALK_CLIENT_ID: response.find((item) => item.key === "DINGTALK_CLIENT_ID")?.value,
        DINGTALK_CLIENT_SECRET: response.find((item) => item.key === "DINGTALK_CLIENT_SECRET")?.value,
        ENABLE_DINGTALK_SYNC: response.find((item) => item.key === "ENABLE_DINGTALK_SYNC")?.value,
        ENABLE_DINGTALK_CONTACT_SYNC: response.find((item) => item.key === "ENABLE_DINGTALK_CONTACT_SYNC")?.value,
      });
    } catch (err) {
      console.error(err);
    }
  };

  const handleGoBack = (e: React.MouseEvent<HTMLAnchorElement, MouseEvent>) => {
    if (isDirty) {
      e.preventDefault();
      setIsDiscardChangesModalOpen(true);
    }
  };

  return (
    <>
      <ConfirmDiscardModal
        isOpen={isDiscardChangesModalOpen}
        onDiscardHref="/authentication"
        handleClose={() => setIsDiscardChangesModalOpen(false)}
      />
      <div className="flex flex-col gap-8">
        <div className="grid w-full grid-cols-2 gap-x-12 gap-y-8">
          <div className="col-span-2 flex flex-col gap-y-4 pt-1 md:col-span-1">
            <div className="pt-2.5 text-18 font-medium">DingTalk-provided details for Plane</div>
            {DINGTALK_FORM_FIELDS.map((field) => (
              <ControllerInput
                key={field.key}
                control={control}
                type={field.type}
                name={field.key}
                label={field.label}
                description={field.description}
                placeholder={field.placeholder}
                error={field.error}
                required={field.required}
              />
            ))}
            {DINGTALK_FORM_SWITCH_FIELDS.map((field) => (
              <ControllerSwitch key={field.name} control={control} field={field} />
            ))}
            <div className="flex flex-col gap-1 pt-4">
              <div className="flex items-center gap-4">
                <Button
                  variant="primary"
                  size="lg"
                  onClick={(e) => void handleSubmit(onSubmit)(e)}
                  loading={isSubmitting}
                  disabled={!isDirty}
                >
                  {isSubmitting ? "Saving" : "Save changes"}
                </Button>
                <Link href="/authentication" className={getButtonStyling("secondary", "lg")} onClick={handleGoBack}>
                  Go back
                </Link>
              </div>
            </div>
          </div>
          <div className="col-span-2 md:col-span-1">
            <div className="flex flex-col gap-y-4 rounded-lg bg-layer-1 px-6 pt-1.5 pb-4">
              <div className="pt-2 text-18 font-medium">Plane-provided details for DingTalk</div>
              {DINGTALK_SERVICE_FIELD.map((field) => (
                <CopyField key={field.key} label={field.label} url={field.url} description={field.description} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
