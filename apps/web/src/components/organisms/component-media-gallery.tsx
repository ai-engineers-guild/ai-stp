"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/atoms/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/atoms/dialog";
import { UI } from "@/lib/ui-selectors";
import { Icon } from "@/theme";

export type ComponentMediaItem = {
  id: string;
  kind: "image" | "video" | "youtube";
  url: string;
  thumbnail_url?: string | null;
  alt: string;
  caption?: string | null;
  source_label: string;
};

export function ComponentMediaGallery({
  items,
  labels,
  locale = "en",
  fallbackAlt,
}: {
  items: ReadonlyArray<ComponentMediaItem>;
  locale?: string;
  fallbackAlt?: string;
  labels: {
    gallery: string;
    open: string;
    source: string;
    close: string;
    previous?: string;
    next?: string;
    typeImage?: string;
    typeVideo?: string;
    typeYoutube?: string;
  };
}) {
  const localizedItems = items.map((item) => ({
    ...item,
    alt: localizedAlt(item.alt, locale, fallbackAlt ?? labels.gallery),
  }));
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [carouselIndex, setCarouselIndex] = useState(0);
  const carouselRef = useRef<HTMLDivElement>(null);
  const selected = selectedIndex === null ? null : localizedItems[selectedIndex];
  if (items.length === 0) return null;

  function selectCarouselSlide(index: number) {
    const nextIndex = Math.max(0, Math.min(localizedItems.length - 1, index));
    setCarouselIndex(nextIndex);
    const slide = carouselRef.current?.children[nextIndex] as HTMLElement | undefined;
    slide?.scrollIntoView({
      behavior: prefersReducedMotion() ? "auto" : "smooth",
      block: "nearest",
      inline: "start",
    });
  }

  return (
    <section
      data-ui={UI.component.mediaGallery}
      aria-labelledby="component-gallery-heading"
      className="min-w-0 space-y-3"
    >
      <h2 id="component-gallery-heading" className="sr-only">
        {labels.gallery}
      </h2>
      <div className="relative">
        <div
          ref={carouselRef}
          role="region"
          aria-roledescription="carousel"
          aria-label={labels.gallery}
          onScroll={() => {
            const node = carouselRef.current;
            const width = node?.clientWidth ?? 0;
            if (width) setCarouselIndex(Math.round((node?.scrollLeft ?? 0) / width));
          }}
          className="flex snap-x snap-mandatory [scrollbar-width:none] overflow-x-auto [&::-webkit-scrollbar]:hidden"
        >
          {localizedItems.map((item, index) => (
            <div key={item.id} className="min-w-full snap-start px-0.5">
              <button
                type="button"
                onClick={() => {
                  setSelectedIndex(index);
                }}
                aria-label={`${labels.open}: ${item.alt}`}
                className="bg-muted focus-visible:ring-ring relative aspect-video min-h-11 w-full overflow-hidden rounded-lg text-left focus-visible:ring-2 focus-visible:outline-none"
              >
                <Media item={item} />
                <MediaTypeBadge item={item} labels={labels} />
                {item.caption ? (
                  <span className="bg-background/80 text-foreground absolute inset-x-0 bottom-0 px-2 py-1 text-xs">
                    {item.caption}
                  </span>
                ) : null}
              </button>
            </div>
          ))}
        </div>
        {localizedItems.length > 1 ? (
          <>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="bg-background/90 absolute top-1/2 left-2 size-11 -translate-y-1/2"
              disabled={carouselIndex === 0}
              aria-label={labels.previous ?? "Previous"}
              onClick={() => {
                selectCarouselSlide(carouselIndex - 1);
              }}
            >
              <Icon name="chevronLeft" size="sm" />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="bg-background/90 absolute top-1/2 right-2 size-11 -translate-y-1/2"
              disabled={carouselIndex === localizedItems.length - 1}
              aria-label={labels.next ?? "Next"}
              onClick={() => {
                selectCarouselSlide(carouselIndex + 1);
              }}
            >
              <Icon name="chevronRight" size="sm" />
            </Button>
          </>
        ) : null}
      </div>
      <MediaLightbox
        items={localizedItems}
        selectedIndex={selectedIndex}
        selected={selected ?? null}
        labels={labels}
        onClose={() => {
          setSelectedIndex(null);
        }}
        onSelect={setSelectedIndex}
      />
    </section>
  );
}

function localizedAlt(alt: string, locale: string, fallback: string): string {
  const value = alt.trim();
  if (value.length < 4) return fallback;
  if (locale !== "ru") return value;
  const letters = Array.from(value).filter((character) => /\p{L}/u.test(character));
  if (letters.length === 0) return fallback;
  const cyrillic = letters.filter((character) => /\p{Script=Cyrillic}/u.test(character)).length;
  return cyrillic / letters.length >= 0.2 ? value : fallback;
}

function MediaLightbox({
  items,
  selectedIndex,
  selected,
  labels,
  onClose,
  onSelect,
}: {
  items: ReadonlyArray<ComponentMediaItem>;
  selectedIndex: number | null;
  selected: ComponentMediaItem | null;
  labels: {
    gallery: string;
    open: string;
    source: string;
    close: string;
    previous?: string;
    next?: string;
    typeImage?: string;
    typeVideo?: string;
    typeYoutube?: string;
  };
  onClose: () => void;
  onSelect: (index: number) => void;
}) {
  const open = selected !== null;
  const previousLabel = labels.previous ?? "Previous";
  const nextLabel = labels.next ?? "Next";

  useEffect(() => {
    if (!open || selectedIndex === null) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        onSelect(Math.max(0, (selectedIndex ?? 0) - 1));
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        onSelect(Math.min(items.length - 1, (selectedIndex ?? 0) + 1));
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
    };
  }, [open, selectedIndex, items.length, onSelect]);

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose();
      }}
    >
      {selected && selectedIndex !== null ? (
        <DialogContent
          data-ui={UI.component.mediaLightbox}
          closeLabel={labels.close}
          className="max-h-[90vh] w-[min(100%,calc(100vw-1.5rem))] max-w-5xl overflow-auto p-4 sm:p-5"
        >
          <DialogTitle className="pr-10">{selected.alt}</DialogTitle>
          <DialogDescription>
            {labels.source}: {selected.source_label}. {selectedIndex + 1} / {items.length}
          </DialogDescription>
          <div className="bg-muted relative overflow-hidden rounded-lg">
            {items.length > 1 ? (
              <>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  className="absolute top-1/2 left-2 z-10 size-11 -translate-y-1/2"
                  disabled={selectedIndex === 0}
                  aria-label={previousLabel}
                  onClick={() => {
                    onSelect(Math.max(0, selectedIndex - 1));
                  }}
                >
                  <Icon name="chevronLeft" size="sm" />
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  className="absolute top-1/2 right-2 z-10 size-11 -translate-y-1/2"
                  disabled={selectedIndex === items.length - 1}
                  aria-label={nextLabel}
                  onClick={() => {
                    onSelect(Math.min(items.length - 1, selectedIndex + 1));
                  }}
                >
                  <Icon name="chevronRight" size="sm" />
                </Button>
              </>
            ) : null}
            <MediaTypeBadge item={selected} labels={labels} />
            <Media
              item={selected}
              expanded
              active
              visible={open}
              label={`${selectedIndex + 1} / ${items.length}`}
            />
          </div>
        </DialogContent>
      ) : null}
    </Dialog>
  );
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return true;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function Media({
  item,
  expanded = false,
  active = false,
  visible = false,
  label,
}: {
  item: ComponentMediaItem;
  expanded?: boolean;
  active?: boolean;
  visible?: boolean;
  label?: string;
}) {
  const [failed, setFailed] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const [inView, setInView] = useState(true);
  const [pageVisible, setPageVisible] = useState(true);

  useEffect(() => {
    if (!expanded) return;
    function onVisibility() {
      setPageVisible(document.visibilityState === "visible");
    }
    document.addEventListener("visibilitychange", onVisibility);
    onVisibility();
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [expanded]);

  useEffect(() => {
    if (!expanded || !frameRef.current) return;
    const node = frameRef.current;
    const observer = new IntersectionObserver(
      ([entry]) => {
        setInView(entry?.isIntersecting ?? false);
      },
      { threshold: 0.4 },
    );
    observer.observe(node);
    return () => {
      observer.disconnect();
    };
  }, [expanded, item.id]);

  const shouldAutoplay =
    expanded && active && visible && inView && pageVisible && !prefersReducedMotion();

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (shouldAutoplay) {
      video.muted = true;
      void video.play().catch(() => undefined);
      return;
    }
    try {
      video.pause();
    } catch {
      /* jsdom implements pause as a throw */
    }
  }, [shouldAutoplay, item.id]);

  if (failed) {
    return (
      <div
        role="img"
        aria-label={item.alt}
        className="bg-muted text-muted-foreground flex aspect-video h-full w-full flex-col items-center justify-center gap-2 p-6 text-center"
      >
        <span className="font-medium">{item.alt}</span>
        <span className="text-xs">{item.source_label}</span>
      </div>
    );
  }
  if (item.kind === "video") {
    return (
      <div ref={frameRef}>
        <video
          ref={videoRef}
          src={item.url}
          poster={item.thumbnail_url || undefined}
          aria-label={label ?? item.alt}
          muted
          preload="metadata"
          playsInline
          controls={expanded}
          disablePictureInPicture
          onError={() => {
            setFailed(true);
          }}
          className={`${expanded ? "max-h-[70vh] object-contain" : "h-full object-cover"} w-full`}
        />
      </div>
    );
  }
  if (item.kind === "youtube") {
    const videoId = item.url;
    if (!expanded) {
      return (
        <img
          src={item.thumbnail_url || `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`}
          alt={item.alt}
          width={1280}
          height={720}
          loading="lazy"
          decoding="async"
          onError={() => {
            setFailed(true);
          }}
          className="h-full w-full object-cover"
        />
      );
    }
    const autoplay = shouldAutoplay ? 1 : 0;
    return (
      <div ref={frameRef} className="aspect-video w-full">
        <iframe
          src={`https://www.youtube-nocookie.com/embed/${videoId}?autoplay=${autoplay}&mute=1&controls=1`}
          title={label ?? item.alt}
          allow="autoplay; encrypted-media; picture-in-picture"
          referrerPolicy="strict-origin-when-cross-origin"
          loading="lazy"
          className="h-full w-full border-0"
        />
      </div>
    );
  }
  return (
    <img
      src={expanded ? item.url : item.thumbnail_url || item.url}
      alt={item.alt}
      width={1280}
      height={720}
      loading="lazy"
      decoding="async"
      onError={() => {
        setFailed(true);
      }}
      className={`${expanded ? "mx-auto max-h-[70vh] object-contain" : "h-full object-cover"} w-full`}
    />
  );
}

function mediaTypeLabel(
  item: ComponentMediaItem,
  labels: { typeImage?: string; typeVideo?: string; typeYoutube?: string },
) {
  if (item.kind === "youtube") return labels.typeYoutube ?? "YouTube";
  if (item.kind === "video") return labels.typeVideo ?? "Video";
  return labels.typeImage ?? "Image";
}

function MediaTypeBadge({
  item,
  labels,
}: {
  item: ComponentMediaItem;
  labels: { typeImage?: string; typeVideo?: string; typeYoutube?: string };
}) {
  return (
    <span className="bg-background/90 text-foreground absolute top-2 left-2 inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium shadow-sm">
      <Icon name={item.kind === "image" ? "camera" : "play"} size="sm" aria-hidden="true" />
      {mediaTypeLabel(item, labels)}
    </span>
  );
}
