export default function AboutPage() {
  return (
    <div className="min-h-screen">
      <div className="container mx-auto max-w-3xl px-4 py-10 sm:px-6 lg:px-8">
        <section className="rounded-lg border border-border bg-card p-6 shadow-sm">
          <h1 className="text-3xl font-display font-bold text-foreground">About iFilm</h1>
          <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
            iFilm is a catalog and playback experience for Mobin Net subscribers. Demo catalog entries may include
            metadata, artwork, and trailer links so administrators can evaluate the publishing workflow before
            commercial rights and full media are attached.
          </p>
        </section>

        <section className="mt-6 rounded-lg border border-border bg-card p-6 shadow-sm" aria-labelledby="credits-heading">
          <h2 id="credits-heading" className="text-xl font-semibold text-foreground">
            Credits and attribution
          </h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            This product uses the TMDB API but is not endorsed or certified by{' '}
            <a
              href="https://www.themoviedb.org/"
              target="_blank"
              rel="noreferrer"
              className="text-primary underline-offset-4 hover:underline"
            >
              TMDB
            </a>
            .
          </p>
        </section>
      </div>
    </div>
  );
}
