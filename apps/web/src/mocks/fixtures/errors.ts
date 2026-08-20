export function errorBody(code: string, caseId: string) {
  return {
    schema_version: 1,
    ok: false,
    request_id: "request_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    operation_id: null,
    error: {
      code,
      message: caseId,
      retryable: false,
      details: {},
    },
    next_actions: [],
  };
}
