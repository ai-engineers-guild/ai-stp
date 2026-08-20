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
    <p className="text-muted-foreground font-mono text-xs" role="status">
      {label}: {operationId}
    </p>
  );
}
