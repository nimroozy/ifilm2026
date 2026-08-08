/** Localize recommendation shelf titles and card explanations (API strings are EN). */

type Sections = Record<string, string | undefined>;

export function localizeRecommendationShelfTitle(
  shelf: { shelf_type: string; title: string; source?: Record<string, unknown> | null },
  sections: Sections
): string {
  const sourceTitle =
    shelf.source && typeof shelf.source.title === 'string' ? shelf.source.title : '';
  switch (shelf.shelf_type) {
    case 'recommended':
      return sections.recommended || shelf.title;
    case 'popular':
      return sections.popularNow || shelf.title;
    case 'new_releases':
      return sections.recentlyAdded || shelf.title;
    case 'top_rated':
      return sections.topRated || shelf.title;
    case 'because_you_watched': {
      const prefix = sections.becauseYouWatched || 'Because You Watched';
      return sourceTitle ? `${prefix} ${sourceTitle}` : prefix;
    }
    case 'editorial_collections':
      return sections.featuredCollections || shelf.title;
    default:
      return shelf.title;
  }
}

/** Map common English reason/explanation phrases for FA/PS UI chrome. */
export function localizeRecommendationExplanation(
  text: string | null | undefined,
  lang: string
): string | undefined {
  if (!text) return undefined;
  if (lang === 'en') return text;

  const fa: Array<[RegExp, string]> = [
    [/^Because you enjoy (.+)$/i, 'چون از $1 لذت می‌برید'],
    [/^Because of actors you like$/i, 'به‌خاطر بازیگرانی که دوست دارید'],
    [/^Similar to (.+)$/i, 'شبیه به $1'],
    [/^Popular in the catalog$/i, 'محبوب در کاتالوگ'],
    [/^Recently added$/i, 'اخیراً اضافه شده'],
    [/^Top rated$/i, 'بالاترین امتیاز'],
    [/^Featured in the catalog$/i, 'ویژه در کاتالوگ'],
    [/^Fits (.+)$/i, 'مناسب $1'],
    [/^Matches (.+) genre$/i, 'مطابق ژانر $1'],
    [/^Relaxed match: ignored (.+)$/i, 'تطبیق منعطف: نادیده گرفتن $1'],
    [/^Matches your preferred (.+) genre$/i, 'مطابق ترجیح ژانر $1 شما'],
  ];
  const ps: Array<[RegExp, string]> = [
    [/^Because you enjoy (.+)$/i, 'ځکه تاسو له $1 څخه خوند اخلئ'],
    [/^Because of actors you like$/i, 'د خوښو لوبغاړو له امله'],
    [/^Similar to (.+)$/i, 'د $1 په څیر'],
    [/^Popular in the catalog$/i, 'په کتلاګ کې مشهور'],
    [/^Recently added$/i, 'نوي اضافه شوی'],
    [/^Top rated$/i, 'لوړ درجه'],
    [/^Featured in the catalog$/i, 'په کتلاګ کې ځانګړی'],
    [/^Fits (.+)$/i, 'د $1 سره سمون'],
    [/^Matches (.+) genre$/i, 'د $1 ژانر سره سمون'],
    [/^Relaxed match: ignored (.+)$/i, 'نرم سمون: $1 پرېښودل شوي'],
    [/^Matches your preferred (.+) genre$/i, 'ستاسو د خوښې $1 ژانر سره سمون'],
  ];
  const table = lang === 'fa' ? fa : lang === 'ps' ? ps : [];
  for (const [re, repl] of table) {
    if (re.test(text)) return text.replace(re, repl);
  }
  return text;
}

export function localizeRelaxedNotes(notes: string[] | undefined, lang: string, labels: Record<string, string>): string | null {
  if (!notes?.length) return null;
  const map: Record<string, { en: string; fa: string; ps: string }> = {
    duration: { en: 'duration', fa: 'مدت', ps: 'موده' },
    'release period': { en: 'release period', fa: 'دوره انتشار', ps: 'د خپرېدو دوره' },
    language: { en: 'language', fa: 'زبان', ps: 'ژبه' },
    subtitles: { en: 'subtitles', fa: 'زیرنویس', ps: 'لیکنې' },
  };
  const localized = notes.map((n) => {
    const row = map[n];
    if (!row) return n;
    if (lang === 'fa') return row.fa;
    if (lang === 'ps') return row.ps;
    return row.en;
  });
  const prefix =
    labels.relaxedPrefix ||
    (lang === 'fa'
      ? 'تطبیق منعطف — برخی فیلترها نادیده گرفته شد'
      : lang === 'ps'
        ? 'نرم سمون — ځینې فلټرونه پرېښودل شوي'
        : 'Relaxed match — some filters were loosened');
  return `${prefix}: ${localized.join(', ')}`;
}
