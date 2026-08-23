"use server";

import { privateApiRequest } from "@/lib/api/http";

export type ComplaintTargetKind = "author" | "component" | "setup" | "other";

export type ComplaintAccepted = {
  schema_version: 1;
  complaint_id: string;
  accepted: true;
};

export async function submitComplaint(input: {
  targetKind: ComplaintTargetKind;
  target: string;
  senderName: string;
  replyEmail: string;
  subject: string;
  message: string;
}): Promise<ComplaintAccepted> {
  return privateApiRequest("/v1/complaints", {
    method: "POST",
    body: {
      schema_version: 1,
      target_kind: input.targetKind,
      target: input.target,
      sender_name: input.senderName,
      reply_email: input.replyEmail,
      subject: input.subject,
      message: input.message,
    },
  });
}
