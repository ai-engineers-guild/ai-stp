const RICKROLL_ID = "dQw4w9WgXcQ";

export function NotFoundRickroll({ label }: { label: string }) {
  return (
    <div className="border-border bg-card aspect-video w-full overflow-hidden rounded-lg border">
      <iframe
        suppressHydrationWarning
        src={`https://www.youtube-nocookie.com/embed/${RICKROLL_ID}?autoplay=1&mute=1&controls=1`}
        title={label}
        allow="autoplay; encrypted-media; picture-in-picture"
        referrerPolicy="strict-origin-when-cross-origin"
        className="h-full w-full border-0"
      />
    </div>
  );
}
