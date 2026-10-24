/** Use configured document language only when every associated direction agrees. */
export function documentLanguage(
  associated: readonly { id: string }[],
  configured: readonly { id: string; language: string }[],
) {
  const languages = associated.map(
    (track) => configured.find((item) => item.id === track.id)?.language,
  );
  if (
    !languages.length ||
    !languages[0] ||
    languages.some((language) => language !== languages[0])
  )
    return undefined;
  try {
    const tag = Intl.getCanonicalLocales(languages[0])[0];
    return new Intl.DisplayNames(["en"], {
      type: "language",
      fallback: "none",
    }).of(tag)
      ? tag
      : undefined;
  } catch {
    return undefined;
  }
}
