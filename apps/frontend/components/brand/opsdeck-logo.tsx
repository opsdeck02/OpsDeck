export function OpsDeckLogo({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3" aria-label="OpsDeck">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-primary text-primaryForeground ring-2 ring-accent/45">
        <svg viewBox="0 0 36 36" className="h-7 w-7" aria-hidden="true">
          <path
            d="M21.2 2.8 7.5 20.2h9L14.8 33.2l14-18.8h-9.3l1.7-11.6Z"
            fill="currentColor"
          />
        </svg>
      </span>
      {!compact ? (
        <span className="text-2xl font-semibold leading-none tracking-normal">
          <span className="text-primary">Ops</span>
          <span className="text-accent">Deck</span>
        </span>
      ) : null}
    </div>
  );
}
