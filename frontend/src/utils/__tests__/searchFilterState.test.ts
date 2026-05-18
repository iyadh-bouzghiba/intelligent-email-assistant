import { describe, it, expect } from 'vitest';
import {
  isSearchQueryActive,
  shouldDisableAttachmentToggle,
  shouldResetAttachmentFilterOnInput,
  resolveSearchEmptyBodyKey,
} from '../searchFilterState';

describe('isSearchQueryActive', () => {
  it('returns false for empty string', () => {
    expect(isSearchQueryActive('')).toBe(false);
  });

  it('returns false for single character', () => {
    expect(isSearchQueryActive('a')).toBe(false);
  });

  it('returns false for whitespace only', () => {
    expect(isSearchQueryActive('  ')).toBe(false);
  });

  it('returns true for 2+ non-whitespace characters', () => {
    expect(isSearchQueryActive('ab')).toBe(true);
    expect(isSearchQueryActive('hello')).toBe(true);
  });

  it('trims whitespace before checking length', () => {
    expect(isSearchQueryActive(' a ')).toBe(false);
    expect(isSearchQueryActive(' ab ')).toBe(true);
  });
});

describe('shouldDisableAttachmentToggle', () => {
  it('returns true when query is too short', () => {
    expect(shouldDisableAttachmentToggle('')).toBe(true);
    expect(shouldDisableAttachmentToggle('a')).toBe(true);
    expect(shouldDisableAttachmentToggle('  ')).toBe(true);
  });

  it('returns false when query meets the threshold', () => {
    expect(shouldDisableAttachmentToggle('ab')).toBe(false);
    expect(shouldDisableAttachmentToggle('search term')).toBe(false);
  });
});

describe('shouldResetAttachmentFilterOnInput', () => {
  it('returns true when next value is empty', () => {
    expect(shouldResetAttachmentFilterOnInput('')).toBe(true);
  });

  it('returns true when next value is whitespace only', () => {
    expect(shouldResetAttachmentFilterOnInput('   ')).toBe(true);
  });

  it('returns false when next value has non-whitespace content', () => {
    expect(shouldResetAttachmentFilterOnInput('a')).toBe(false);
    expect(shouldResetAttachmentFilterOnInput('hello')).toBe(false);
  });
});

describe('resolveSearchEmptyBodyKey', () => {
  it('returns attachment key when hasAttachments is true', () => {
    expect(resolveSearchEmptyBodyKey(true)).toBe('search.no_attachment_results');
  });

  it('returns default key when hasAttachments is false', () => {
    expect(resolveSearchEmptyBodyKey(false)).toBe('search.no_results_body');
  });
});
