import { cn } from "@/lib/cn";
import type { DocsNavNode } from "@/lib/docs-nav";
import { Link } from "@/lib/i18n/navigation";

export function DocsNav({
  tree,
  currentHref,
  ariaLabel,
}: {
  tree: readonly DocsNavNode[];
  currentHref: string;
  ariaLabel: string;
}) {
  return (
    <nav
      aria-label={ariaLabel}
      data-ui="docs-nav"
      className="max-h-[calc(100vh-8rem)] space-y-1 overflow-y-auto text-sm"
    >
      <DocsNavList nodes={tree} currentHref={currentHref} />
    </nav>
  );
}

function DocsNavList({
  nodes,
  currentHref,
}: {
  nodes: readonly DocsNavNode[];
  currentHref: string;
}) {
  return (
    <ul className="space-y-0.5">
      {nodes.map((node) => (
        <li key={`${node.title}:${node.href ?? "group"}`}>
          {node.children?.length ? (
            <div className="mt-3 first:mt-0">
              {node.href ? (
                <NavLink href={node.href} currentHref={currentHref} className="font-medium">
                  {node.title}
                </NavLink>
              ) : (
                <p className="text-muted-foreground px-3 py-1.5 font-medium">{node.title}</p>
              )}
              <div className="border-border ml-2 border-l pl-1">
                <DocsNavList nodes={node.children} currentHref={currentHref} />
              </div>
            </div>
          ) : node.href ? (
            <NavLink href={node.href} currentHref={currentHref}>
              {node.title}
            </NavLink>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function NavLink({
  href,
  currentHref,
  className,
  children,
}: {
  href: string;
  currentHref: string;
  className?: string;
  children: string;
}) {
  const current = href === currentHref;
  return (
    <Link
      href={href}
      aria-current={current ? "page" : undefined}
      className={cn(
        "hover:bg-muted block rounded-sm px-3 py-1.5",
        current && "bg-muted font-medium",
        className,
      )}
    >
      {children}
    </Link>
  );
}
