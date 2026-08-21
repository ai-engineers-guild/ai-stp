const RICKROLL_ID = "dQw4w9WgXcQ";

export function NotFoundRickroll({ label }: { label: string }) {
  return (
    <div className="aspect-video w-full overflow-hidden rounded-lg">
      <iframe
        src={`https://www.youtube-nocookie.com/embed/${RICKROLL_ID}?autoplay=1&mute=0&controls=1`}
        title={label}
        allow="autoplay; encrypted-media; picture-in-picture"
        referrerPolicy="strict-origin-when-cross-origin"
        className="h-full w-full border-0"
      />
    </div>
  );
}
