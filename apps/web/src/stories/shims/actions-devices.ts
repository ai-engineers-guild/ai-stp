/** Storybook no-op for device server actions. */
export async function revokeDeviceAction(_input: {
  deviceId: string;
  etag: string;
  csrfToken: string;
}): Promise<{ operationId: string | null; signedOut: boolean }> {
  return { operationId: "operation_storybook_demo", signedOut: false };
}
