export const isSearchQueryActive = (query: string): boolean =>
  query.trim().length >= 2;

export const shouldDisableAttachmentToggle = (query: string): boolean =>
  query.trim().length < 2;

export const shouldResetAttachmentFilterOnInput = (nextValue: string): boolean =>
  nextValue.trim().length === 0;

export const resolveSearchEmptyBodyKey = (hasAttachments: boolean): string =>
  hasAttachments ? 'search.no_attachment_results' : 'search.no_results_body';
