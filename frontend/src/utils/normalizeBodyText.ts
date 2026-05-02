/**
 * Conservative display-only body normalization for email rendering.
 *
 * What it does:
 *   - Strips a leading BOM (U+FEFF) or zero-width space (U+200B) if present
 *   - Normalizes line endings to \n  (handles \r\n and lone \r)
 *   - Strips a leading standalone orphan wrapper/marker token on its own line.
 *     Exact forms recognized (and ONLY these forms, at the very start of text):
 *       ()  []  {}  (  )  [  ]  {  }
 *     These are artifacts from HTML-to-text parsing (e.g. images with empty alt
 *     attributes, empty anchor tags, empty block elements). The token must occupy
 *     the entire first line — nothing else may follow it on that line.
 *   - Collapses runs of 3+ consecutive blank lines down to exactly 2
 *   - Trims leading and trailing whitespace
 *
 * What it does NOT do:
 *   - Strip quote prefixes (>)
 *   - Detect or cut thread-history markers
 *   - Cap length
 *   - Sanitize HTML
 *   - Remove any bracket/punctuation tokens anywhere except the very first line
 *
 * This is NOT a replacement for sanitizeOriginalExcerpt, which handles
 * quote-context extraction for the outbound reply body. Use this function
 * only for display rendering in reading surfaces.
 */
export function normalizeBodyText(text: string): string {
  if (!text) return '';

  // Strip leading BOM or zero-width space
  let s = text.replace(/^[\uFEFF\u200B]+/, '');

  // Normalize line endings
  s = s.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

  // Strip a leading standalone orphan wrapper/marker token.
  // Matches ONLY these exact token forms at the very start of the string:
  //   ()  []  {}  (  )  [  ]  {  }
  // The token must be followed by optional horizontal whitespace then a
  // newline or end-of-string — i.e. it must be the entire first line.
  // Nothing mid-body is ever touched.
  s = s.replace(/^(?:\(\)|\[\]|\{\}|[(){}[\]])[^\S\n]*(?:\n|$)/, '');

  // Collapse 3+ consecutive blank lines to 2
  s = s.replace(/\n{3,}/g, '\n\n');

  // Trim outer whitespace
  return s.trim();
}
