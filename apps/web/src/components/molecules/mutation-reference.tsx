type MutationReferenceProps = {
  label: string;
  operationId: string | null | undefined;
};

/** Small mono audit reference after a successful mutation. */
export function MutationReference({ label, operationId }: MutationReferenceProps) {
  if (!operationId) {
    return null;
  }
  return (
    <p className="font-mono text-xs text-muted-foreground" role="status">
      {label}: {operationId}
    </p>
  );
}
